# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import hashlib
import hmac
import json
import uuid
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from plane.db.models import IssueActivity, IssueComment, IssueLink, Notification
from plane.ext.github import cache, tasks, views
from plane.ext.github.ci import DIDNT_RUN, FAILED_VERDICT, PASSED
from plane.ext.models import ActivityProvenance
from plane.ext.tests.conftest import make_issue
from plane.settings.redis import redis_instance

SECRET = "s3cret"
REPO = "Acme/App"
PR = 7
URL = f"https://github.com/{REPO.lower()}/pull/{PR}"
SHA = "a" * 40
URL_PATH = "/api/github/webhook/"


def sign(body, secret=SECRET):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def repository():
    return {"full_name": REPO, "default_branch": "main"}


def pull(**extra):
    return {"number": PR, "head": {"sha": SHA}, "base": {"ref": "main"}, "draft": False, **extra}


def pr_event(action, **extra):
    return {"action": action, "pull_request": pull(**extra), "repository": repository(), "sender": {"login": "octo"}}


def run_event(action, conclusion=None, run_id=1, attempt=1, prs=(PR,), name="CI", sha=SHA, branch="feature"):
    run = {
        "id": run_id,
        "run_attempt": attempt,
        "name": name,
        "head_sha": sha,
        "head_branch": branch,
        "conclusion": conclusion,
        "pull_requests": [{"number": n, "head": {"sha": sha}} for n in prs],
    }
    return {"action": action, "workflow_run": run, "repository": repository(), "sender": {"login": "octo"}}


def job_event(name, conclusion, run_id=1, attempt=1, job_id=None):
    job = {
        "id": job_id or abs(hash((name, run_id, attempt))),
        "run_id": run_id,
        "run_attempt": attempt,
        "name": name,
        "head_sha": SHA,
        "head_branch": "feature",
        "conclusion": conclusion,
    }
    return {"action": "completed", "workflow_job": job, "repository": repository(), "sender": {"login": "octo"}}


def status_event(context, state, sha=SHA):
    return {
        "sha": sha,
        "context": context,
        "state": state,
        "updated_at": timezone.now().isoformat(),
        "branches": [{"name": "feature"}],
        "repository": repository(),
        "sender": {"login": "octo"},
    }


@pytest.fixture
def issue(project):
    return make_issue(project, "PR item")


@pytest.fixture
def env(monkeypatch, project):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GITHUB_WEBHOOK_REPOS", f"{REPO}={project.id},other/repo=not-a-uuid")
    monkeypatch.setenv("GITHUB_WEBHOOK_CLIENT_AGENT", "squadronapp")
    monkeypatch.delenv("GITHUB_WEBHOOK_ACTOR", raising=False)


@pytest.fixture(autouse=True)
def clean_redis():
    r = redis_instance()
    for key in r.scan_iter(f"{cache.PREFIX}*"):
        r.delete(key)
    yield
    for key in r.scan_iter(f"{cache.PREFIX}*"):
        r.delete(key)


@pytest.fixture
def scheduled(monkeypatch):
    """Record the retries and CI evaluations the tasks schedule, instead of sending them to a broker."""
    calls = {"retry": [], "ci": []}
    monkeypatch.setattr(tasks, "_schedule_retry", lambda repo, what: calls["retry"].append((repo, what)))
    monkeypatch.setattr(tasks, "_schedule_ci", lambda *args: calls["ci"].append(args))
    return calls


@pytest.fixture
def linked(issue):
    IssueLink.objects.create(issue=issue, project=issue.project, workspace=issue.workspace, url=URL)
    return issue


def deliver(event, payload, delivery=None):
    tasks.github_delivery(delivery or str(uuid.uuid4()), event, payload)


def rows(issue=None, **filters):
    qs = IssueActivity.objects.filter(field="github", **filters)
    if issue is not None:
        qs = qs.filter(issue=issue)
    return list(qs.order_by("created_at"))


def settle(issue):
    """Age the checks rows past the CI settle window, then run the evaluation."""
    IssueActivity.objects.filter(issue=issue, verb="checks").update(created_at=timezone.now() - timedelta(minutes=1))
    tasks.github_ci(str(issue.project_id), str(issue.id), URL, SHA)


def verdicts(issue):
    return [json.loads(r.new_value)["verdict"] for r in rows(issue, verb="ci")]


# the endpoint


@pytest.mark.django_db
class TestEndpoint:
    @pytest.fixture(autouse=True)
    def queued(self, monkeypatch):
        calls = []
        monkeypatch.setattr(views.github_delivery, "delay", lambda *args: calls.append(args))
        return calls

    def post(self, body, event="pull_request", signature=None, delivery="d-1"):
        headers = {"HTTP_X_GITHUB_EVENT": event, "HTTP_X_GITHUB_DELIVERY": delivery}
        if signature is not None:
            headers["HTTP_X_HUB_SIGNATURE_256"] = signature
        return Client().post(URL_PATH, data=body, content_type="application/json", **headers)

    def test_off_without_a_secret(self, monkeypatch, queued):
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        body = b"{}"
        assert self.post(body, signature=sign(body)).status_code == 404
        assert queued == []

    @pytest.mark.parametrize("signature", [None, "", "sha256=00", sign(b"{}", "wrong")])
    def test_bad_or_missing_signature_is_401(self, env, queued, signature):
        assert self.post(b"{}", signature=signature).status_code == 401
        assert queued == []

    def test_ping_answers_200_and_queues_nothing(self, env, queued):
        body = json.dumps({"zen": "hi"}).encode()
        assert self.post(body, event="ping", signature=sign(body)).status_code == 200
        assert queued == []

    def test_signed_event_is_queued_with_202(self, env, queued):
        body = json.dumps(pr_event("closed", merged=True)).encode()
        response = self.post(body, signature=sign(body), delivery="d-9")
        assert response.status_code == 202
        assert queued == [("d-9", "pull_request", json.loads(body))]

    def test_get_is_refused(self, env):
        assert Client().get(URL_PATH).status_code == 405


# PR → item and the verbs


@pytest.mark.django_db
def test_merged_row_on_the_linked_item(env, linked, scheduled):
    deliver("pull_request", pr_event("closed", merged=True, merge_commit_sha="m" * 40), delivery="d-1")
    [row] = rows(linked)
    value = json.loads(row.new_value)
    assert (row.verb, row.old_value, row.actor_id, row.attachments) == ("merged", "d-1", None, [])
    assert value["pr"] == URL and value["head_sha"] == SHA and value["login"] == "octo"
    assert value["merge_sha"] == "m" * 40
    assert row.comment == "PR merged"
    provenance = ActivityProvenance.objects.get(activity=row)
    assert (provenance.channel, provenance.client_agent) == ("api", "squadronapp")
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_actor_comes_from_env(env, linked, scheduled, monkeypatch, create_user):
    monkeypatch.setenv("GITHUB_WEBHOOK_ACTOR", str(create_user.id))
    deliver("pull_request", pr_event("reopened"))
    assert rows(linked)[0].actor_id == create_user.id


@pytest.mark.django_db
def test_deliver_comment_links_the_pr(env, issue, scheduled, create_user):
    IssueComment.objects.create(
        issue=issue,
        project=issue.project,
        workspace=issue.workspace,
        actor=create_user,
        comment_html=f'<p>deliver — <a href="{URL}">{URL}</a> is ready</p>',
    )
    deliver("pull_request", pr_event("closed", merged=False))
    assert [r.verb for r in rows(issue)] == ["closed"]


@pytest.mark.django_db
def test_other_comments_and_other_prs_do_not_link(env, issue, scheduled, create_user):
    IssueComment.objects.create(
        issue=issue,
        project=issue.project,
        workspace=issue.workspace,
        actor=create_user,
        comment_html=f"<p>see {URL}</p>",
    )
    IssueLink.objects.create(issue=issue, project=issue.project, workspace=issue.workspace, url=URL + "0")
    deliver("pull_request", pr_event("reopened"))
    assert rows() == []


@pytest.mark.django_db
def test_redelivery_is_skipped(env, linked, scheduled):
    payload = pr_event("synchronize", before="b" * 40)
    deliver("pull_request", payload, delivery="same")
    deliver("pull_request", payload, delivery="same")
    assert len(rows(linked)) == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event,payload,verb,line,extra",
    [
        ("pull_request", pr_event("closed", merged=False), "closed", "PR closed without merging", {}),
        ("pull_request", pr_event("reopened"), "reopened", "PR reopened", {"draft": False}),
        ("pull_request", pr_event("synchronize", before="b" * 40), "pushed", "pushed aaaaaaa", {"before": "b" * 40}),
        ("pull_request", pr_event("ready_for_review"), "draft", "PR marked ready for review", {"draft": False}),
        ("pull_request", pr_event("converted_to_draft", draft=True), "draft", "PR converted to draft", {"draft": True}),
        (
            "pull_request_review",
            {
                "action": "submitted",
                "review": {"state": "approved", "user": {"login": "rev"}, "commit_id": SHA, "html_url": "r"},
                "pull_request": pull(),
                "repository": repository(),
                "sender": {"login": "rev"},
            },
            "review",
            "rev approved",
            {"state": "approved"},
        ),
        (
            "issue_comment",
            {
                "action": "created",
                "issue": {"number": PR, "pull_request": {"url": "x"}},
                "comment": {"user": {"login": "c"}, "html_url": "cu"},
                "repository": repository(),
                "sender": {"login": "c"},
            },
            "comment",
            "c commented",
            {"comment_url": "cu", "head_sha": None},
        ),
        (
            "pull_request_review_comment",
            {
                "action": "created",
                "pull_request": pull(),
                "comment": {"user": {"login": "c"}, "html_url": "cu", "commit_id": SHA},
                "repository": repository(),
                "sender": {"login": "c"},
            },
            "comment",
            "c commented",
            {"comment_url": "cu", "head_sha": SHA},
        ),
    ],
)
def test_each_verb(env, linked, scheduled, event, payload, verb, line, extra):
    deliver(event, payload)
    [row] = rows(linked)
    assert (row.verb, row.comment) == (verb, line)
    value = json.loads(row.new_value)
    assert value["pr"] == URL
    for key, expected in extra.items():
        assert value[key] == expected


@pytest.mark.django_db
def test_push_to_default_branch_writes_base_moved_without_an_item(env, project, scheduled):
    payload = {"ref": "refs/heads/main", "before": "1" * 40, "after": "2" * 40, "repository": repository()}
    deliver("push", payload)
    deliver("push", {**payload, "ref": "refs/heads/feature"})
    [row] = rows(verb="base-moved")
    assert row.issue_id is None and row.project_id == project.id
    assert json.loads(row.new_value)["sha"] == "2" * 40
    assert len(rows()) == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event,payload",
    [
        ("installation", {"action": "created", "repository": repository()}),
        ("pull_request", pr_event("opened")),
        ("pull_request", pr_event("labeled")),
        ("issue_comment", {"action": "created", "issue": {"number": 1}, "comment": {}, "repository": repository()}),
        ("pull_request", {**pr_event("closed", merged=True), "repository": {"full_name": "someone/else"}}),
    ],
)
def test_ignored_events_write_nothing(env, linked, scheduled, event, payload):
    deliver(event, payload)
    assert rows() == []


@pytest.mark.django_db
def test_unlinked_pr_writes_nothing_and_waits_in_redis(env, issue, scheduled):
    deliver("pull_request", pr_event("closed", merged=True))
    assert rows() == []
    assert cache.waiting(REPO.lower(), f"pr:{PR}")
    assert scheduled["retry"] == [(REPO.lower(), f"pr:{PR}")]
    deliver("pull_request", pr_event("reopened"))
    assert len(scheduled["retry"]) == 1  # one retry chain per key


# CI


def ci_run(*jobs, conclusion="success", run_id=1, attempt=1, name="CI"):
    deliver("workflow_run", run_event("requested", run_id=run_id, attempt=attempt, name=name))
    for job, result in jobs:
        deliver("workflow_job", job_event(job, result, run_id=run_id, attempt=attempt))
    deliver("workflow_run", run_event("completed", conclusion, run_id=run_id, attempt=attempt, name=name))


@pytest.mark.django_db
def test_ci_passed(env, linked, scheduled):
    ci_run(("build", "success"), ("test", "success"))
    assert {r.verb for r in rows(linked)} == {"checks"}
    assert scheduled["ci"][-1] == (str(linked.project_id), str(linked.id), URL, SHA, 30)
    settle(linked)
    [row] = rows(linked, verb="ci")
    assert (row.comment, row.old_value) == ("CI passed", "")
    assert json.loads(row.new_value) == {"pr": URL, "head_sha": SHA, "verdict": PASSED, "failed": []}


@pytest.mark.django_db
def test_ci_failed_names_the_failing_jobs_and_statuses(env, linked, scheduled):
    ci_run(("build", "success"), ("test", "failure"), conclusion="failure")
    deliver("status", status_event("React Doctor", "error"))
    settle(linked)
    [row] = rows(linked, verb="ci")
    assert json.loads(row.new_value)["failed"] == ["React Doctor", "test"]
    assert row.comment == "CI failed: React Doctor, test"


@pytest.mark.django_db
def test_ci_waits_while_anything_is_pending(env, linked, scheduled):
    ci_run(("build", "success"))
    deliver("status", status_event("React Doctor", "pending"))
    settle(linked)
    assert verdicts(linked) == []
    deliver("status", status_event("React Doctor", "success"))
    settle(linked)
    assert verdicts(linked) == [PASSED]


@pytest.mark.django_db
def test_ci_waits_30s_after_the_last_completion(env, linked, scheduled):
    ci_run(("build", "success"))
    scheduled["ci"].clear()
    tasks.github_ci(str(linked.project_id), str(linked.id), URL, SHA)
    assert verdicts(linked) == []
    [call] = scheduled["ci"]
    assert 1 <= call[-1] <= 31


@pytest.mark.django_db
def test_ci_didnt_run_is_held_until_the_pr_is_seen_ready(env, linked, scheduled):
    ci_run(("build", "skipped"), conclusion="skipped")
    settle(linked)
    assert verdicts(linked) == []  # no row says the PR is ready
    deliver("pull_request", pr_event("ready_for_review"))
    assert scheduled["ci"][-1][-1] == 0
    settle(linked)
    assert verdicts(linked) == [DIDNT_RUN]


@pytest.mark.django_db
def test_a_draft_holds_every_verdict(env, linked, scheduled):
    deliver("pull_request", pr_event("converted_to_draft", draft=True))
    ci_run(("build", "success"))
    settle(linked)
    assert verdicts(linked) == []
    deliver("pull_request", pr_event("ready_for_review"))
    settle(linked)
    assert verdicts(linked) == [PASSED]


@pytest.mark.django_db
def test_a_late_run_that_changes_the_verdict_writes_a_new_row(env, linked, scheduled):
    ci_run(("test", "success"))
    settle(linked)
    settle(linked)  # same verdict again writes nothing
    ci_run(("lint", "failure"), conclusion="failure", run_id=2, name="Lint")
    settle(linked)
    assert verdicts(linked) == [PASSED, FAILED_VERDICT]


@pytest.mark.django_db
def test_a_rerun_that_passes_replaces_the_failed_attempt(env, linked, scheduled):
    ci_run(("test", "failure"), conclusion="failure")
    settle(linked)
    ci_run(("test", "success"), attempt=2)
    settle(linked)
    assert verdicts(linked) == [FAILED_VERDICT, PASSED]


@pytest.mark.django_db
def test_a_repo_with_no_ci_gets_no_ci_row(env, linked, scheduled):
    deliver("pull_request", pr_event("synchronize", before="b" * 40))
    settle(linked)
    assert verdicts(linked) == []


@pytest.mark.django_db
def test_status_finds_its_pr_through_the_head_seen_on_open(env, linked, scheduled):
    deliver("pull_request", pr_event("opened"))  # writes nothing, remembers the head
    deliver("status", status_event("React Doctor", "success"))
    [row] = rows(linked)
    assert (row.verb, json.loads(row.new_value)["pr"]) == ("checks", URL)


@pytest.mark.django_db
def test_status_before_its_pr_is_known_waits_for_the_head(env, linked, scheduled):
    deliver("status", status_event("React Doctor", "success"))
    assert rows() == [] and cache.waiting(REPO.lower(), f"sha:{SHA}")
    deliver("pull_request", pr_event("opened"))
    assert [r.verb for r in rows(linked)] == ["checks"]


@pytest.mark.django_db
def test_ci_on_the_default_branch_is_ignored(env, linked, scheduled):
    deliver("workflow_run", run_event("completed", "success", prs=(), branch="main"))
    assert rows() == [] and not cache.waiting(REPO.lower(), f"sha:{SHA}")


# events that arrive before the link


@pytest.mark.django_db
def test_a_run_that_completes_before_the_link_is_written_once_linked(env, issue, scheduled):
    ci_run(("build", "success"))
    assert rows() == [] and scheduled["ci"] == []
    IssueLink.objects.create(issue=issue, project=issue.project, workspace=issue.workspace, url=URL)
    tasks.github_retry(REPO.lower(), f"pr:{PR}")
    assert len(rows(issue, verb="checks")) == 3
    assert not cache.waiting(REPO.lower(), f"pr:{PR}")
    assert scheduled["ci"]
    settle(issue)
    assert verdicts(issue) == [PASSED]


@pytest.mark.django_db
def test_a_retry_before_the_link_parks_the_events_again(env, issue, scheduled):
    deliver("pull_request", pr_event("closed", merged=True))
    tasks.github_retry(REPO.lower(), f"pr:{PR}")
    assert rows() == [] and cache.waiting(REPO.lower(), f"pr:{PR}")
    assert len(scheduled["retry"]) == 2


@pytest.mark.django_db
def test_a_cached_event_expires_unlinked(env, issue, scheduled, monkeypatch):
    deliver("pull_request", pr_event("closed", merged=True))
    later = cache.now() + cache.TTL + 1
    monkeypatch.setattr(cache, "now", lambda: later)
    IssueLink.objects.create(issue=issue, project=issue.project, workspace=issue.workspace, url=URL)
    tasks.github_retry(REPO.lower(), f"pr:{PR}")
    assert rows() == []
    assert not cache.waiting(REPO.lower(), f"pr:{PR}")


# the v1 activity API


@pytest.mark.django_db
def test_activity_api_hides_checks_rows(env, linked, scheduled, api_key_client, workspace):
    ci_run(("build", "success"))
    settle(linked)
    url = f"/api/v1/workspaces/{workspace.slug}/projects/{linked.project_id}/work-items/{linked.id}/activities/"
    body = api_key_client.get(url).json()
    verbs = [row["verb"] for row in body["results"] if row["field"] == "github"]
    assert verbs == ["ci"]
