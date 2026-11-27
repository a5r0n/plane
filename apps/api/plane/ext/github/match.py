# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Find the work item a PR belongs to, and the PR a head sha belongs to."""

import html
import json
import re

from django.utils.html import strip_tags

from plane.db.models import IssueActivity, IssueComment, IssueLink

# the same rules Squadron's Tower uses to read an item's PR
PR_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
DELIVER_RE = re.compile(r"^\s*deliver —")


def _names(text, url):
    return any(found.lower() == url.lower() for found in PR_RE.findall(text or ""))


def item_for(project_id, url):
    """The id of the item whose Links hold the PR url, else whose `deliver —` comment names it; newest wins."""
    found = []
    links = IssueLink.objects.filter(project_id=project_id, url__icontains=url, issue__deleted_at__isnull=True)
    for link in links.only("issue_id", "url", "created_at"):
        if _names(link.url, url):
            found.append((link.created_at, link.issue_id))
    comments = IssueComment.objects.filter(
        project_id=project_id, comment_html__icontains=url, issue__deleted_at__isnull=True
    )
    for comment in comments.only("issue_id", "comment_html", "created_at"):
        text = html.unescape(strip_tags(comment.comment_html))
        if DELIVER_RE.match(text) and _names(comment.comment_html, url):
            found.append((comment.created_at, comment.issue_id))
    return str(max(found)[1]) if found else None


def pr_for_sha(project_id, sha):
    """The PR url the newest `github` row with this head sha names, or None."""
    rows = IssueActivity.objects.filter(
        project_id=project_id,
        field="github",
        issue__isnull=False,
        new_value__contains=json.dumps({"head_sha": sha})[1:-1],
    ).order_by("-created_at")
    for row in rows.only("new_value")[:5]:
        try:
            pr = json.loads(row.new_value).get("pr")
        except (TypeError, ValueError):
            continue
        if pr:
            return pr
    return None
