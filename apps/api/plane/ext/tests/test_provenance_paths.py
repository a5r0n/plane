# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Provenance on the activity rows written outside the issue_activity bulk insert."""

from unittest import mock

import pytest
from celery.signals import before_task_publish
from django.db import connection

from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import IssueActivity
from plane.ext.models import ActivityProvenance, CustomProperty, WorkItemStep
from plane.ext.tests.conftest import make_issue, make_project

CLIENT = {"HTTP_X_CLIENT_SESSION": "sess-7", "HTTP_X_CLIENT_AGENT": "pilot"}


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Provenance", "PV")


@pytest.fixture
def item(project):
    return make_issue(project, "Traced")


@pytest.fixture(autouse=True)
def no_webhooks():
    with (
        mock.patch("plane.ext.steps.webhook_activity.delay"),
        mock.patch("plane.ext.properties.webhook_activity.delay"),
    ):
        yield


def items_url(project, tail=""):
    return f"/api/v1/workspaces/{project.workspace.slug}/projects/{project.id}/work-items/{tail}"


def provenance_of(activity):
    row = ActivityProvenance.objects.get(activity=activity)
    return row.channel, row.api_token_id, row.client_session, row.client_agent


@pytest.mark.django_db
def test_item_create_records_the_created_row(clients, api_token, project):
    """The request's thread: publish handler stamps the message, the task writes the created row."""

    def publish(*args, **kwargs):
        headers = {}
        before_task_publish.send(sender=issue_activity.name, headers=headers, body=None)
        issue_activity.apply(kwargs={**kwargs, "notification": False}, headers=headers)

    with mock.patch.object(issue_activity, "delay", side_effect=publish):
        response = clients.api_key.post(items_url(project), {"name": "New one"}, format="json", **CLIENT)
    assert response.status_code == 201, response.data

    created = IssueActivity.objects.get(issue_id=response.data["id"], verb="created", field__isnull=True)
    assert provenance_of(created) == ("api", api_token.id, "sess-7", "pilot")


@pytest.mark.django_db
def test_step_add_over_the_api(clients, api_token, item):
    response = clients.api_key.post(
        items_url(item.project, f"{item.id}/steps/"), {"title": "Build"}, format="json", **CLIENT
    )
    assert response.status_code == 201, response.data

    activity = IssueActivity.objects.get(issue=item, field="step")
    assert provenance_of(activity) == ("api", api_token.id, "sess-7", "pilot")


@pytest.mark.django_db
def test_property_set_over_the_api(clients, api_token, item, create_user):
    for key in ("repo", "note"):
        CustomProperty.objects.create(
            project=item.project, workspace=item.workspace, key=key, name=key, type="text", created_by=create_user
        )
    response = clients.api_key.patch(
        items_url(item.project, f"{item.id}/"),
        {"custom_fields": {"repo": "plane", "note": "hi"}},
        format="json",
        **CLIENT,
    )
    assert response.status_code == 200, response.data

    activities = IssueActivity.objects.filter(issue=item, field="custom_fields")
    assert activities.count() == 2
    assert {provenance_of(a) for a in activities} == {("api", api_token.id, "sess-7", "pilot")}


@pytest.mark.django_db
def test_step_add_from_the_web_app_is_the_app_channel(clients, item):
    url = f"/api/workspaces/{item.workspace.slug}/projects/{item.project_id}/issues/{item.id}/steps/"
    response = clients.session.post(url, {"title": "Build"}, format="json")
    assert response.status_code == 201, response.data

    activity = IssueActivity.objects.get(issue=item, field="step")
    assert provenance_of(activity) == ("app", None, "", "")


def broken_insert(*args, **kwargs):
    """A database error that aborts the open transaction, as a failed insert would."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1/0")


@pytest.mark.django_db
def test_a_provenance_failure_keeps_the_step_and_its_activity(clients, item):
    with mock.patch.object(ActivityProvenance.objects, "bulk_create", side_effect=broken_insert):
        response = clients.api_key.post(items_url(item.project, f"{item.id}/steps/"), {"title": "Build"}, format="json")
    assert response.status_code == 201, response.data
    assert WorkItemStep.objects.filter(issue=item).count() == 1
    activity = IssueActivity.objects.get(issue=item, field="step")
    assert not ActivityProvenance.objects.filter(activity=activity).exists()
