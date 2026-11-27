# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Celery side of the GitHub webhook: write rows, park the ones whose PR isn't linked yet, and judge CI."""

import json
import logging

from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone

from plane.db.models import IssueActivity
from plane.ext.github import cache, ci, config, events, match
from plane.ext.models import ActivityProvenance

log = logging.getLogger("plane.ext.github")


def _lock(name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"squadron-github:{name}"])


def _write(project_id, issue_id, verb, value, line, old_value):
    activity = IssueActivity.objects.create(
        issue_id=issue_id,
        project_id=project_id,
        workspace_id=_workspace(project_id),
        actor_id=config.actor(),
        verb=verb,
        field="github",
        old_value=old_value,
        new_value=json.dumps(value),
        comment=line[:255],
        attachments=[],
        epoch=int(timezone.now().timestamp()),
    )
    ActivityProvenance.objects.create(
        activity=activity, channel=ActivityProvenance.Channel.API, client_agent=config.client_agent()
    )
    return activity


def _workspace(project_id):
    from plane.db.models import Project

    return Project.objects.values_list("workspace_id", flat=True).get(pk=project_id)


def _write_once(project_id, issue_id, delivery, fact, value):
    """Write the row unless this delivery already wrote one for this item; True when written."""
    with transaction.atomic():
        _lock(f"delivery:{delivery}")
        seen = IssueActivity.objects.filter(
            project_id=project_id, issue_id=issue_id, field="github", verb=fact["verb"], old_value=delivery
        )
        if fact["verb"] == "checks":  # one delivery may carry several runs' facts only through several PRs
            seen = seen.filter(new_value=json.dumps(value))
        if seen.exists():
            return False
        _write(project_id, issue_id, fact["verb"], value, fact["line"], delivery)
        return True


def _schedule_retry(repo, what):
    github_retry.apply_async((repo, what), countdown=cache.RETRY)


def _schedule_ci(project_id, issue_id, url, sha, countdown):
    github_ci.apply_async((project_id, issue_id, url, sha), countdown=countdown)


def handle(repo, project_id, entry):
    """Write one fact, or park it in Redis until its PR is linked."""
    fact, delivery = entry["fact"], entry["delivery"]
    value = {"repo": repo, "login": entry.get("login"), **fact["data"]}
    if fact["verb"] == "base-moved":
        value["sha"] = fact["sha"]
        _write_once(project_id, None, delivery, fact, value)
        return
    if fact["pr"]:
        url = events.pr_url(repo, fact["pr"])
    else:
        number = cache.head(repo, fact["sha"]) if fact["sha"] else None
        url = events.pr_url(repo, number) if number else match.pr_for_sha(project_id, fact["sha"])
        if url is None:
            cache.wait(repo, f"sha:{fact['sha']}", entry, _schedule_retry)
            return
    issue_id = match.item_for(project_id, url)
    if issue_id is None:
        cache.wait(repo, f"pr:{url.rsplit('/', 1)[1]}", entry, _schedule_retry)
        return
    value = {"pr": url, "head_sha": fact["sha"], **value}
    if not _write_once(project_id, issue_id, delivery, fact, value):
        return
    if fact["verb"] == "checks":
        _schedule_ci(project_id, issue_id, url, fact["sha"], ci.SETTLE)
    elif fact["verb"] == "draft" and not fact["data"]["draft"] and fact["sha"]:
        _schedule_ci(project_id, issue_id, url, fact["sha"], 0)


@shared_task
def github_delivery(delivery, event, payload):
    repo = ((payload.get("repository") or {}).get("full_name") or "").lower()
    project_id = config.repos().get(repo)
    if not project_id:
        return
    login = (payload.get("sender") or {}).get("login")
    found = events.heads(event, payload)
    for sha, number in found:
        cache.remember_head(repo, sha, number)
    for fact in events.facts(event, payload):
        handle(repo, project_id, {"delivery": delivery, "login": login, "fact": fact, "received": cache.now()})
    for sha, _ in found:
        if cache.waiting(repo, f"sha:{sha}"):
            github_retry(repo, f"sha:{sha}")


@shared_task
def github_retry(repo, what):
    """Retry the entries parked under `what`; one still unlinked parks again until its hour is up."""
    project_id = config.repos().get(repo)
    for entry in cache.take(repo, what):
        if project_id:
            handle(repo, project_id, entry)


def _rows(issue_id, url):
    rows = IssueActivity.objects.filter(issue_id=issue_id, field="github", new_value__contains=url).order_by(
        "created_at"
    )
    for row in rows.only("verb", "new_value", "created_at"):
        try:
            value = json.loads(row.new_value)
        except (TypeError, ValueError):
            continue
        if value.get("pr") == url:
            yield row, value


def _completed(data):
    if data.get("kind") == "run":
        return data.get("status") == "completed"
    if data.get("kind") == "status":
        return data.get("state") != "pending"
    return True


@shared_task
def github_ci(project_id, issue_id, url, sha):
    """Write a `ci` row for the PR head once its checks settle, when the verdict changed."""
    wait = _judge(project_id, issue_id, url, sha)
    if wait:
        _schedule_ci(project_id, issue_id, url, sha, wait)


def _judge(project_id, issue_id, url, sha):
    """Write the verdict if it's due; return seconds to wait when the checks haven't settled yet."""
    with transaction.atomic():
        _lock(f"ci:{url}:{sha}")
        checks, draft, last = [], None, None
        for row, value in _rows(issue_id, url):
            if "draft" in value:
                draft = value["draft"]
            if row.verb == "checks" and value.get("head_sha") == sha:
                checks.append((row.created_at, value))
            elif row.verb == "ci" and value.get("head_sha") == sha:
                last = (value.get("verdict"), value.get("failed") or [])
        result = ci.verdict(checks)
        if result is None or result[0] == "pending":
            return
        done = max(at for at, data in checks if _completed(data))
        wait = ci.SETTLE - (timezone.now() - done).total_seconds()
        if wait > 0:
            return int(wait) + 1
        # a draft holds every verdict; a PR never seen as ready holds only "didn't run"
        if draft or (draft is None and result[0] == ci.DIDNT_RUN):
            return
        if last == (result[0], result[1]):
            return
        value = {"pr": url, "head_sha": sha, "verdict": result[0], "failed": result[1]}
        _write(project_id, issue_id, "ci", value, ci.line(*result), "")
