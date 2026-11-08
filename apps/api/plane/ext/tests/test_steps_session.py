# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid
from unittest import mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from rest_framework import status

from plane.authentication.session import BaseSessionAuthentication
from plane.db.models import IssueActivity
from plane.ext.models import WorkItemStep
from plane.ext.steps import (
    SessionStepDetailEndpoint,
    SessionStepListCreateEndpoint,
    SessionStepReorderEndpoint,
    SessionStepSetPathEndpoint,
)
from plane.ext.tests.conftest import make_issue, make_project


def view_of(path):
    func = resolve(path).func
    return getattr(func, "__wrapped__", func).cls


@pytest.mark.unit
def test_session_routes_resolve_to_session_views():
    base = f"/api/workspaces/acme/projects/{uuid.uuid4()}/issues/{uuid.uuid4()}/steps/"
    assert view_of(base) is SessionStepListCreateEndpoint
    assert view_of(base + "set-path/") is SessionStepSetPathEndpoint
    assert view_of(base + "reorder/") is SessionStepReorderEndpoint
    assert view_of(base + f"{uuid.uuid4()}/") is SessionStepDetailEndpoint
    assert SessionStepDetailEndpoint.authentication_classes == [BaseSessionAuthentication]


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Steps", "ST")


@pytest.fixture
def item(project):
    return make_issue(project, "Ship it")


@pytest.fixture
def client(clients):
    with mock.patch("plane.ext.steps.webhook_activity.delay"):
        yield clients.session


def url(issue, tail=""):
    return f"/api/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/steps/{tail}"


def add(client, issue, **body):
    return client.post(url(issue), body, format="json")


@pytest.mark.contract
@pytest.mark.django_db
class TestSessionSteps:
    def test_crud_reorder_and_set_path(self, client, item):
        a = add(client, item, title="build").json()
        b = add(client, item, title="ship").json()
        assert add(client, item, title="test", position=1).status_code == status.HTTP_201_CREATED
        done = client.patch(url(item, f"{a['id']}/"), {"status": "failed", "note": "red"}, format="json")
        assert (done.json()["status"], done.json()["note"]) == ("failed", "red")
        ids = [s["id"] for s in client.get(url(item)).json()]
        moved = client.post(url(item, "reorder/"), {"step_ids": list(reversed(ids))}, format="json")
        assert [s["title"] for s in moved.json()] == ["ship", "test", "build"]
        path = client.post(url(item, "set-path/"), {"steps": [{"id": b["id"]}, {"title": "new"}]}, format="json")
        assert [s["title"] for s in path.json()] == ["ship", "new"]
        assert client.delete(url(item, f"{b['id']}/")).status_code == status.HTTP_204_NO_CONTENT
        assert [s["title"] for s in client.get(url(item)).json()] == ["new"]

    def test_writes_record_step_activity_seen_on_the_history_route(self, client, item):
        add(client, item, title="build")
        history = client.get(
            f"/api/workspaces/{item.workspace.slug}/projects/{item.project_id}/issues/{item.id}/history/",
            {"activity_type": "issue-property"},  # what the web app sends
        )
        assert history.status_code == status.HTTP_200_OK
        rows = [row for row in history.json() if row.get("field") == "step"]
        assert [row["comment"] for row in rows] == ["added step 'build'"]
        assert IssueActivity.objects.filter(issue=item, field="step").count() == 1

    def test_an_api_key_alone_is_not_a_session(self, clients, item):
        assert clients.api_key.get(url(item)).status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        assert clients.anon.get(url(item)).status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def summary_of(body, issue):
    rows = body["results"] if isinstance(body, dict) else body
    if isinstance(rows, dict):  # grouped: {group: {"results": [...]}}
        rows = [row for group in rows.values() for row in group["results"]]
    return next(row for row in rows if row["id"] == str(issue.id))["step_summary"]


@pytest.mark.contract
@pytest.mark.django_db
class TestListRows:
    def list_url(self, project):
        return f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/issues/"

    def test_rows_carry_a_step_summary(self, client, project, item, create_user):
        bare = make_issue(project, "No steps")
        first = add(client, item, title="build").json()
        skipped = add(client, item, title="lint").json()
        add(client, item, title="ship", actor=str(create_user.id))
        client.patch(url(item, f"{first['id']}/"), {"status": "done"}, format="json")
        client.patch(url(item, f"{skipped['id']}/"), {"status": "skipped"}, format="json")
        body = client.get(self.list_url(project)).json()
        summary = summary_of(body, item)
        assert (summary["done"], summary["total"]) == (2, 3)
        assert summary["current"]["title"] == "ship" and summary["current"]["actor"] == str(create_user.id)
        assert summary_of(body, bare) is None

    def test_grouped_rows_carry_it_too(self, client, project, item):
        add(client, item, title="build")
        body = client.get(self.list_url(project), {"group_by": "state_id"}).json()
        assert summary_of(body, item)["current"]["title"] == "build"

    def test_a_failed_step_stays_current(self, client, project, item):
        step = add(client, item, title="build").json()
        add(client, item, title="ship")
        client.patch(url(item, f"{step['id']}/"), {"status": "failed", "note": "red"}, format="json")
        current = summary_of(client.get(self.list_url(project)).json(), item)["current"]
        assert (current["title"], current["status"]) == ("build", "failed")

    def test_one_query_for_the_summaries(self, client, project):
        for n in range(5):
            issue = make_issue(project, f"item {n}")
            WorkItemStep.objects.create(issue=issue, project=project, workspace=project.workspace, title="s")
        with CaptureQueriesContext(connection) as few:
            client.get(self.list_url(project))
        steps_queries = [q for q in few.captured_queries if "squadron_ext_work_item_steps" in q["sql"]]
        assert len(steps_queries) == 1
