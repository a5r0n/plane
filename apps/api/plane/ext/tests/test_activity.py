# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
from celery.signals import before_task_publish
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import resolve
from django.utils import timezone

from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import APIToken, IssueActivity, IssueComment
from plane.ext import provenance
from plane.ext.activity import ActivityDetailAPIEndpoint, ActivityListAPIEndpoint
from plane.ext.models import ActivityProvenance
from plane.ext.tests.conftest import make_issue


def view_of(path):
    func = resolve(path).func
    return getattr(func, "__wrapped__", func).cls


def stamped(request):
    """The headers before_task_publish leaves on an issue_activity message sent during `request`."""
    headers = {}
    with mock.patch.object(provenance, "get_current_request", return_value=request):
        provenance.stamp_provenance(sender=provenance.TASK, headers=headers)
    return headers


def run_comment_task(issue, user, headers, html="<p>hi</p>"):
    """Run issue_activity for a new comment the way a worker would, with `headers` on the message."""
    comment = IssueComment.objects.create(
        issue=issue, project=issue.project, workspace=issue.workspace, actor=user, comment_html=html
    )
    issue_activity.apply(
        kwargs={
            "type": "comment.activity.created",
            "requested_data": json.dumps({"id": str(comment.id), "comment_html": html}),
            "current_instance": None,
            "issue_id": str(issue.id),
            "actor_id": str(user.id),
            "project_id": str(issue.project_id),
            "epoch": int(timezone.now().timestamp()),
        },
        headers=headers,
    )
    return IssueActivity.objects.get(issue_comment=comment)


def api_request(token=None, **headers):
    meta = {f"HTTP_{name.upper().replace('-', '_')}": value for name, value in headers.items()}
    if token:
        meta["HTTP_X_API_KEY"] = token
    return RequestFactory().post("/", **meta)


@pytest.fixture
def issue(project):
    return make_issue(project, "Activity one")


@pytest.fixture
def activities_url(v1, issue):
    return lambda tail="": v1(f"work-items/{issue.id}/activities/{tail}")


@pytest.mark.unit
@pytest.mark.parametrize("items", ["work-items", "issues"])
def test_activity_routes_resolve_to_ext_views(items):
    base = f"/api/v1/workspaces/acme/projects/{uuid.uuid4()}/{items}/{uuid.uuid4()}/activities/"
    assert view_of(base) is ActivityListAPIEndpoint
    assert view_of(base + f"{uuid.uuid4()}/") is ActivityDetailAPIEndpoint


@pytest.mark.unit
def test_publish_handler_is_connected():
    assert provenance.stamp_provenance in before_task_publish._live_receivers(provenance.TASK)


@pytest.mark.django_db
def test_list_includes_comments_and_hides_votes_reactions_drafts(api_key_client, issue, create_user, activities_url):
    for field in ("comment", "name", "vote", "reaction", "draft"):
        IssueActivity.objects.create(
            issue=issue,
            project=issue.project,
            workspace=issue.workspace,
            actor=create_user,
            verb="created",
            field=field,
        )
    response = api_key_client.get(activities_url())
    assert response.status_code == 200
    assert sorted(row["field"] for row in response.data["results"]) == ["comment", "name"]
    assert all(row["provenance"] is None for row in response.data["results"])


@pytest.mark.django_db
def test_detail_serves_a_comment_and_404s_a_vote(api_key_client, issue, create_user, activities_url):
    rows = {
        field: IssueActivity.objects.create(
            issue=issue,
            project=issue.project,
            workspace=issue.workspace,
            actor=create_user,
            verb="created",
            field=field,
        )
        for field in ("comment", "vote")
    }
    response = api_key_client.get(activities_url(f"{rows['comment'].id}/"))
    assert response.status_code == 200
    assert response.data["field"] == "comment"
    assert response.data["provenance"] is None
    assert api_key_client.get(activities_url(f"{rows['vote'].id}/")).status_code == 404


@pytest.mark.django_db
def test_api_key_with_client_headers_reaches_the_list(api_key_client, api_token, issue, create_user, activities_url):
    headers = stamped(api_request(api_token.token, **{"X-Client-Session": "sess-1", "X-Client-Agent": "pilot"}))
    assert headers[provenance.HEADER] == {
        "channel": "api",
        "token": str(api_token.id),
        "session": "sess-1",
        "agent": "pilot",
    }
    activity = run_comment_task(issue, create_user, headers)

    response = api_key_client.get(activities_url())
    row = next(row for row in response.data["results"] if row["id"] == activity.id)
    assert row["field"] == "comment"
    assert row["provenance"] == {
        "channel": "api",
        "token": {"id": str(api_token.id), "label": api_token.label},
        "session": "sess-1",
        "agent": "pilot",
    }
    assert api_token.token not in json.dumps(response.data, default=str)


@pytest.mark.django_db
def test_api_key_without_client_headers(api_token, issue, create_user):
    activity = run_comment_task(issue, create_user, stamped(api_request(api_token.token)))
    row = activity.squadron_provenance
    assert (row.channel, row.api_token_id, row.client_session, row.client_agent) == ("api", api_token.id, "", "")


@pytest.mark.django_db
def test_session_request_is_the_app_channel(issue, create_user):
    request = api_request(**{"X-Client-Agent": "browser"})
    request.user = create_user
    activity = run_comment_task(issue, create_user, stamped(request))
    row = activity.squadron_provenance
    assert (row.channel, row.api_token_id, row.client_agent) == ("app", None, "browser")


@pytest.mark.django_db
def test_no_request_or_anonymous_leaves_no_provenance(issue, create_user):
    anonymous = api_request()
    anonymous.user = AnonymousUser()
    assert stamped(None) == {}
    assert stamped(anonymous) == {}
    activity = run_comment_task(issue, create_user, {})
    assert not ActivityProvenance.objects.filter(activity=activity).exists()


@pytest.mark.unit
def test_other_tasks_are_not_stamped(api_token):
    headers = {}
    with mock.patch.object(provenance, "get_current_request", return_value=api_request("x")):
        provenance.stamp_provenance(sender="plane.bgtasks.notification_task.notifications", headers=headers)
    assert headers == {}


@pytest.mark.django_db
def test_long_client_headers_are_truncated(api_token):
    headers = stamped(api_request(api_token.token, **{"X-Client-Session": "s" * 300, "X-Client-Agent": "a" * 300}))
    assert len(headers[provenance.HEADER]["session"]) == 255
    assert len(headers[provenance.HEADER]["agent"]) == 255


@pytest.mark.django_db
def test_deleted_token_gives_null_token(api_key_client, api_token, issue, create_user, activities_url):
    other = APIToken.objects.create(user=create_user, label="Gone", token="gone-token")
    activity = run_comment_task(issue, create_user, stamped(api_request(other.token)))
    other.delete()

    response = api_key_client.get(activities_url(f"{activity.id}/"))
    assert response.data["provenance"]["channel"] == "api"
    assert response.data["provenance"]["token"] is None


@pytest.mark.django_db
def test_token_deleted_before_the_task_runs(issue, create_user):
    other = APIToken.objects.create(user=create_user, label="Gone", token="gone-early")
    headers = stamped(api_request(other.token))
    other.delete()
    row = run_comment_task(issue, create_user, headers).squadron_provenance
    assert (row.channel, row.api_token_id) == ("api", None)


@pytest.mark.unit
def test_worker_request_attribute_is_read():
    # a worker exposes message headers as attributes of task.request, not under request.headers
    task = SimpleNamespace(request=SimpleNamespace(squadron_provenance={"channel": "api"}, headers=None))
    with mock.patch.object(provenance, "current_task", task):
        assert provenance.task_provenance() == {"channel": "api"}


@pytest.mark.django_db
def test_a_provenance_failure_keeps_the_activity(api_token, issue, create_user):
    with mock.patch.object(ActivityProvenance.objects, "bulk_create", side_effect=RuntimeError("boom")):
        activity = run_comment_task(issue, create_user, stamped(api_request(api_token.token)))
    assert activity.field == "comment"
    assert not ActivityProvenance.objects.filter(activity=activity).exists()


@pytest.mark.django_db
def test_a_real_v1_comment_request_carries_its_headers(api_key_client, api_token, issue, v1, activities_url):
    """The request's own thread: DRF auth, crum's current request, the publish handler, then the task."""

    def publish(**kwargs):
        headers = {}
        before_task_publish.send(sender=issue_activity.name, headers=headers, body=None)
        issue_activity.apply(kwargs={**kwargs, "notification": False}, headers=headers)

    with mock.patch("plane.api.views.issue.issue_activity.delay", side_effect=publish):
        response = api_key_client.post(
            v1(f"work-items/{issue.id}/comments/"),
            {"comment_html": "<p>via api</p>"},
            format="json",
            HTTP_X_CLIENT_SESSION="sess-9",
            HTTP_X_CLIENT_AGENT="drone",
        )
    assert response.status_code == 201, response.data

    rows = api_key_client.get(activities_url()).data["results"]
    row = next(row for row in rows if row["field"] == "comment")
    assert row["provenance"]["channel"] == "api"
    assert row["provenance"]["token"]["id"] == str(api_token.id)
    assert (row["provenance"]["session"], row["provenance"]["agent"]) == ("sess-9", "drone")
