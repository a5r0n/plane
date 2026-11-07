# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta
from uuid import uuid4

import pytest
from django.urls import resolve
from django.utils import timezone

import plane.app.urls
from plane.db.models import Issue
from plane.ext.epics import routes
from plane.ext.epics.urls import alias_patterns
from plane.ext.tests.helpers import results

pytestmark = pytest.mark.django_db

EXPECTED_ALIAS_COUNT = 26


def test_create_stamps_the_type(session_client, url):
    r = session_client.post(url("epics/"), {"name": "E"}, format="json")
    assert r.status_code == 201, r.content
    assert Issue.objects.get(pk=r.json()["id"]).type.is_epic


def test_create_with_a_form_encoded_body(session_client, url):
    r = session_client.post(url("epics/"), {"name": "E"})  # multipart, immutable QueryDict
    assert r.status_code == 201, r.content
    assert Issue.objects.get(pk=r.json()["id"]).type.is_epic


def test_create_in_an_unknown_project(session_client, workspace):
    r = session_client.post(f"/api/workspaces/{workspace.slug}/projects/{uuid4()}/epics/", {"name": "E"}, format="json")
    assert 400 <= r.status_code < 500


def test_list_shows_only_epics_and_counts_children(session_client, url, epic, normal, child_of_epic):
    rows = results(session_client.get(url("epics/")))
    assert [r["id"] for r in rows] == [str(epic.id)]
    assert rows[0]["sub_issues_count"] == 1
    assert rows[0]["is_epic"] is True


def test_sub_issues_add_and_ring(session_client, url, epic, normal, done_state):
    r = session_client.post(url(f"epics/{epic.id}/issues/"), {"sub_issue_ids": [str(normal.id)]}, format="json")
    assert r.status_code == 200, r.content
    Issue.objects.filter(pk=normal.id).update(state=done_state)
    body = session_client.get(url(f"epics/{epic.id}/issues/")).json()
    assert [s["id"] for s in body["sub_issues"]] == [str(normal.id)]
    assert body["state_distribution"]["completed"] == [str(normal.id)]


@pytest.mark.parametrize("sent,row", [("epic-property", "activity"), ("epic-comment", "comment")])
def test_history_takes_epic_activity_types(session_client, url, epic_with_history, sent, row):
    """Upstream's unmatched branch sorts model instances, so this needs real rows to fail."""
    r = session_client.get(url(f"epics/{epic_with_history.epic.id}/history/"), {"activity_type": sent})
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [str(getattr(epic_with_history, row).id)]


def test_archive_comments_links(session_client, url, epic, completed_state):
    Issue.objects.filter(pk=epic.id).update(state=completed_state, completed_at=timezone.now() - timedelta(days=2))
    r = session_client.post(url(f"epics/{epic.id}/comments/"), {"comment_html": "<p>x</p>"}, format="json")
    assert r.status_code == 201, r.content
    r = session_client.post(url(f"epics/{epic.id}/links/"), {"url": "https://example.com"}, format="json")
    assert r.status_code == 201, r.content
    assert session_client.post(url(f"epics/{epic.id}/archive/")).status_code == 200


def test_by_id_routes_mark_epics(session_client, url, workspace, epic, normal):
    assert session_client.get(url(f"issues/{epic.id}/")).json()["is_epic"] is True
    assert session_client.get(url(f"issues/{normal.id}/")).json().get("is_epic", False) is False
    by_key = f"/api/workspaces/{workspace.slug}/work-items/EP-{epic.sequence_id}/"
    assert session_client.get(by_key).json()["is_epic"] is True


def test_every_alias_source_still_exists():
    """A renamed upstream route must fail here, not vanish."""
    upstream = {str(p.pattern) for p in plane.app.urls.urlpatterns}
    assert not (set(routes.ALIASES) - upstream)
    assert not (set(routes.MARKED) - upstream)
    assert len(alias_patterns()) == EXPECTED_ALIAS_COUNT


def test_epic_routes_resolve_to_our_wrappers(workspace, project, epic):
    match = resolve(f"/api/workspaces/{workspace.slug}/projects/{project.id}/epics/{epic.id}/history/")
    assert match.url_name.startswith("squadron-epic-")
