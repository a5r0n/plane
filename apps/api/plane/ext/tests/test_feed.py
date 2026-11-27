# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import asyncio
import json
import time
from datetime import timedelta
from urllib.parse import urlencode

import pytest
from asgiref.sync import sync_to_async
from asgiref.testing import ApplicationCommunicator
from django.core.cache import cache
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIClient

from plane.db.models import APIToken, IssueActivity, ProjectMember
from plane.ext.feed import READER_TTL, WorkspaceActivityFeedEndpoint, reader_key
from plane.ext.models import ActivityProvenance
from plane.ext.tests.conftest import make_issue, make_project


def add_row(issue, field="name", ago=None, project=None, **extra):
    project = project or issue.project
    row = IssueActivity.objects.create(
        issue=issue, project=project, workspace=project.workspace, verb="updated", field=field, **extra
    )
    if ago is not None:
        IssueActivity.objects.filter(pk=row.pk).update(created_at=timezone.now() - ago)
        row.refresh_from_db()
    return row


def ids(body):
    return [row["id"] for row in body["results"]]


@pytest.fixture
def issue(project):
    return make_issue(project, "Feed one")


@pytest.fixture
def feed(workspace, api_key_client):
    def call(client=None, **params):
        params = {name: value for name, value in params.items() if value is not None}
        response = (client or api_key_client).get(f"/api/v1/workspaces/{workspace.slug}/activities/", params)
        return response.status_code, response.json()

    return call


@pytest.fixture
def during_hold(monkeypatch):
    """Run a callback inside the next call that waits, as if newer calls overtook it."""
    hold = WorkspaceActivityFeedEndpoint.hold

    def install(callback):
        def patched(self, wait, poll):
            if wait:
                monkeypatch.setattr(WorkspaceActivityFeedEndpoint, "hold", hold)
                callback()
            return hold(self, wait, poll)

        monkeypatch.setattr(WorkspaceActivityFeedEndpoint, "hold", patched)

    return install


@pytest.fixture
def other_client(create_user):
    token = APIToken.objects.create(user=create_user, label="Other token", token="other-api-token-67890")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.mark.unit
def test_route_resolves_to_feed_view():
    func = resolve("/api/v1/workspaces/acme/activities/").func
    assert getattr(func, "__wrapped__", func).cls is WorkspaceActivityFeedEndpoint


@pytest.mark.contract
class TestReader:
    def test_new_reader_gets_recent_rows_with_identifier(self, feed, issue):
        row = add_row(issue)
        status, body = feed(reader="new")
        assert status == 200
        assert body["reader"] and body["batch"] and body["more"] is False
        [got] = [r for r in body["results"] if r["id"] == str(row.id)]
        assert got["issue_identifier"] == f"EP-{issue.sequence_id}"
        assert "provenance" in got

    def test_reader_used_by_another_token_is_refused(self, feed, issue, other_client):
        add_row(issue)
        _, body = feed(reader="new")
        status, refused = feed(client=other_client, reader=body["reader"], ack=body["batch"])
        assert status == 403 and refused["code"] == "READER_FORBIDDEN"
        # the refused ack didn't count for the owner
        _, again = feed(reader=body["reader"])
        assert ids(again) == ids(body)

    def test_expired_or_unknown_reader_is_gone(self, feed, issue):
        _, body = feed(reader="new")
        cache.delete(reader_key(body["reader"]))
        assert feed(reader=body["reader"])[0] == 410
        status, gone = feed(reader="never-issued")
        assert status == 410 and gone["code"] == "READER_GONE"

    def test_reader_expires_after_ten_idle_minutes(self, feed, issue):
        _, body = feed(reader="new")
        assert READER_TTL == 600
        assert 590 <= cache.ttl(reader_key(body["reader"])) <= READER_TTL
        cache.expire(reader_key(body["reader"]), 5)
        feed(reader=body["reader"])
        # every call starts the idle clock again
        assert 590 <= cache.ttl(reader_key(body["reader"])) <= READER_TTL

    def test_ack_marks_the_batch_delivered(self, feed, issue):
        add_row(issue)
        _, first = feed(reader="new")
        assert first["results"]
        _, second = feed(reader=first["reader"], ack=first["batch"])
        assert second["results"] == [] and second["batch"] is None

    def test_unacked_batch_is_sent_again(self, feed, issue):
        add_row(issue)
        _, first = feed(reader="new")
        _, second = feed(reader=first["reader"])
        assert ids(second) == ids(first)
        # a stale batch id is ignored: the rows still come
        _, third = feed(reader=first["reader"], ack=first["batch"])
        assert ids(third) == ids(first)
        _, fourth = feed(reader=first["reader"], ack=third["batch"])
        assert fourth["results"] == []

    def test_two_readers_are_independent(self, feed, issue):
        add_row(issue)
        _, a = feed(reader="new")
        _, b = feed(reader="new")
        assert a["reader"] != b["reader"]
        feed(reader=a["reader"], ack=a["batch"])
        _, b_again = feed(reader=b["reader"])
        assert ids(b_again) == ids(b) and b_again["results"]

    def test_late_row_inside_the_window_is_delivered(self, feed, issue):
        _, first = feed(reader="new")
        late = add_row(issue, ago=timedelta(minutes=5))
        _, second = feed(reader=first["reader"], ack=first["batch"])
        assert str(late.id) in ids(second)

    def test_rows_outside_the_window_are_not_sent(self, feed, issue):
        old = add_row(issue, ago=timedelta(minutes=11))
        _, body = feed(reader="new")
        assert str(old.id) not in ids(body)

    def test_redated_description_row_is_delivered_again(self, feed, issue):
        row = add_row(issue, field="description")
        _, first = feed(reader="new")
        assert str(row.id) in ids(first)
        _, acked = feed(reader=first["reader"], ack=first["batch"])
        assert acked["results"] == []
        # what track_description does when the same actor edits again
        row.created_at = timezone.now()
        row.save(update_fields=["created_at"])
        _, again = feed(reader=first["reader"])
        assert ids(again) == [str(row.id)]

    def test_per_page_pages_through_with_more(self, feed, issue):
        rows = [add_row(issue) for _ in range(3)]
        _, first = feed(reader="new", per_page=2)
        assert first["more"] is True and ids(first) == [str(r.id) for r in rows[:2]]
        _, second = feed(reader=first["reader"], ack=first["batch"], per_page=2)
        assert second["more"] is False and ids(second) == [str(rows[2].id)]

    def test_overtaken_held_call_keeps_newer_acks(self, feed, issue, during_hold):
        _, first = feed(reader="new")
        reader = first["reader"]
        newer = {}

        def overtake():
            newer["row"] = add_row(issue)
            _, delivered = feed(reader=reader, ack=first["batch"])
            feed(reader=reader, ack=delivered["batch"])

        during_hold(overtake)
        _, held = feed(reader=reader, wait=1)
        assert held["results"] == [] and held["batch"] is None
        _, after = feed(reader=reader)
        assert str(newer["row"].id) not in ids(after)

    def test_overtaken_held_call_keeps_newer_batch(self, feed, issue, during_hold):
        _, first = feed(reader="new")
        reader = first["reader"]
        newer = {}

        def overtake():
            add_row(issue)
            _, newer["page"] = feed(reader=reader, ack=first["batch"])

        during_hold(overtake)
        _, held = feed(reader=reader, wait=1)
        assert held["results"] == []
        assert newer["page"]["results"]
        _, after = feed(reader=reader, ack=newer["page"]["batch"])
        assert after["results"] == []

    def test_wait_times_out_empty(self, feed, issue):
        _, first = feed(reader="new")
        started = time.monotonic()
        _, body = feed(reader=first["reader"], ack=first["batch"], wait=1)
        assert body["results"] == []
        assert 0.9 <= time.monotonic() - started < 5


@pytest.mark.contract
class TestRows:
    def test_filters(self, feed, issue, other_project):
        other = make_issue(other_project, "Elsewhere")
        name = add_row(issue, field="name")
        state = add_row(issue, field="state")
        elsewhere = add_row(other, field="name")
        by_pilot = add_row(issue, field="labels")
        ActivityProvenance.objects.create(activity=by_pilot, channel="api", client_agent="pilot")

        def got(**params):
            return set(ids(feed(reader="new", **params)[1]))

        assert got(project=str(other_project.id)) == {str(elsewhere.id)}
        assert got(field="state,labels") == {str(state.id), str(by_pilot.id)}
        assert str(name.id) not in got(exclude_field="name")
        assert str(state.id) in got(exclude_field="name")
        assert got(agent="pilot") == {str(by_pilot.id)}

    def test_hidden_fields_left_out(self, feed, issue):
        vote = add_row(issue, field="vote")
        comment = add_row(issue, field="comment")
        result = ids(feed(reader="new")[1])
        assert str(vote.id) not in result and str(comment.id) in result

    def test_only_active_member_projects(self, feed, workspace, create_user, issue):
        stranger_project = make_project(workspace, create_user, "Stranger", "ST")
        ProjectMember.objects.filter(project=stranger_project, member=create_user).update(is_active=False)
        hidden = add_row(make_issue(stranger_project, "Not mine"))
        assert str(hidden.id) not in ids(feed(reader="new")[1])

    def test_soft_deleted_membership_left_out(self, feed, workspace, create_user, issue):
        gone_project = make_project(workspace, create_user, "Gone", "GN")
        ProjectMember.objects.filter(project=gone_project, member=create_user).update(deleted_at=timezone.now())
        hidden = add_row(make_issue(gone_project, "Was mine"))
        assert str(hidden.id) not in ids(feed(reader="new")[1])

    def test_archived_project_left_out(self, feed, issue, other_project):
        hidden = add_row(make_issue(other_project, "Archived"))
        other_project.archived_at = timezone.now()
        other_project.save(update_fields=["archived_at"])
        assert str(hidden.id) not in ids(feed(reader="new")[1])

    def test_epic_rows_are_shown(self, feed, project):
        epic = make_issue(project, "An epic", epic=True)
        row = add_row(epic)
        [got] = [r for r in feed(reader="new")[1]["results"] if r["id"] == str(row.id)]
        assert got["issue_identifier"] == f"EP-{epic.sequence_id}"

    def test_row_with_no_item(self, feed, project):
        row = IssueActivity.objects.create(
            issue=None, project=project, workspace=project.workspace, verb="deleted", field="issue"
        )
        [got] = [r for r in feed(reader="new")[1]["results"] if r["id"] == str(row.id)]
        assert got["issue_identifier"] is None

    def test_since_without_reader(self, feed, issue):
        old = add_row(issue, ago=timedelta(hours=2))
        recent = add_row(issue, ago=timedelta(minutes=30))
        since = (timezone.now() - timedelta(hours=1)).isoformat()
        status, body = feed(since=since)
        assert status == 200 and "reader" not in body
        assert str(recent.id) in ids(body) and str(old.id) not in ids(body)

    @pytest.mark.parametrize(
        "params",
        [{}, {"reader": "new", "since": "2026-01-01T00:00:00Z"}, {"since": "yesterday"}, {"reader": "new", "wait": 26}],
    )
    def test_bad_params(self, feed, params):
        assert feed(**params)[0] == 400

    @pytest.mark.parametrize("name", ["field", "exclude_field", "agent", "reader"])
    def test_nul_byte_is_a_bad_param(self, feed, name):
        params = {"reader": "new", name: "a\x00b"}
        status, body = feed(**params)
        assert status == 400 and body["code"] == "INVALID_PARAM"

    def test_bad_project_filter(self, feed):
        assert feed(reader="new", project="not-a-uuid")[0] == 400


# Through the real ASGI app: Django's test client skips the per-request thread that keeps a held view off the loop.
async def asgi_get(path, params, token):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": urlencode(params).encode(),
        "headers": [(b"host", b"testserver"), (b"x-api-key", token.encode())],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    from plane.asgi import application

    communicator = ApplicationCommunicator(application, scope)
    await communicator.send_input({"type": "http.request", "body": b"", "more_body": False})
    start = await communicator.receive_output(timeout=40)
    body = b""
    while True:
        message = await communicator.receive_output(timeout=40)
        body += message.get("body", b"")
        if not message.get("more_body"):
            break
    await communicator.wait()
    return start["status"], json.loads(body or b"null"), time.monotonic()


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
class TestHeldRequests:
    def test_new_row_wakes_a_held_request(self, workspace, project, api_token):
        issue = make_issue(project, "Wake")
        path = f"/api/v1/workspaces/{workspace.slug}/activities/"

        async def scenario():
            _, first, _ = await asgi_get(path, {"reader": "new"}, api_token.token)
            started = time.monotonic()
            held = asyncio.ensure_future(
                asgi_get(path, {"reader": first["reader"], "ack": first["batch"] or "", "wait": 10}, api_token.token)
            )
            await asyncio.sleep(1.5)
            # a late row: committed now, dated inside the window
            late = await sync_to_async(add_row)(issue, ago=timedelta(minutes=2))
            status, body, done = await held
            return late, status, body, done - started

        late, status, body, elapsed = asyncio.run(scenario())
        assert status == 200 and ids(body) == [str(late.id)]
        assert elapsed < 7

    def test_held_request_does_not_delay_another(self, workspace, project, api_token):
        path = f"/api/v1/workspaces/{workspace.slug}/activities/"

        async def scenario():
            _, first, _ = await asgi_get(path, {"reader": "new"}, api_token.token)
            held_params = {"reader": first["reader"], "ack": first["batch"] or "", "wait": 6}
            started = time.monotonic()
            held = asyncio.ensure_future(asgi_get(path, held_params, api_token.token))
            await asyncio.sleep(0.5)
            quick_status, _, quick_done = await asgi_get(path, {"since": timezone.now().isoformat()}, api_token.token)
            held_status, held_body, held_done = await held
            return quick_status, quick_done - started, held_status, held_body, held_done - started

        quick_status, quick_elapsed, held_status, held_body, held_elapsed = asyncio.run(scenario())
        assert quick_status == 200 and quick_elapsed < 3.5
        assert held_status == 200 and held_body["results"] == [] and held_elapsed >= 5.5
