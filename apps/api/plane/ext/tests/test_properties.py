# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest import mock

import pytest
from django.db import IntegrityError, transaction
from rest_framework import status

from plane.db.models import Issue, IssueActivity, ProjectMember, User, WorkspaceMember
from plane.db.models.api import APIToken
from plane.ext.models import CustomProperty, CustomValue
from plane.ext.properties import coerce, present
from plane.ext.tests.conftest import make_issue, make_project

T = CustomProperty.Type


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Props", "PR")


@pytest.fixture
def define(project, create_user):
    def define(key, type, **fields):
        fields.setdefault("name", key.title())
        return CustomProperty.objects.create(
            project=project, workspace=project.workspace, key=key, type=type, created_by=create_user, **fields
        )

    return define


def held(prop, **column):
    return CustomValue(property=prop, **column)


@pytest.mark.unit
@pytest.mark.django_db
class TestCoerce:
    def test_text(self, define):
        prop = define("note", T.TEXT)
        assert coerce(prop, "ok") == ["ok"]
        for bad in ("a\nb", "x" * 256, 5, ["ok"]):
            with pytest.raises(ValueError):
                coerce(prop, bad)

    def test_number(self, define):
        prop = define("count", T.NUMBER)
        assert coerce(prop, "1.5") == [Decimal("1.5")]
        assert coerce(prop, 3) == [Decimal(3)]
        for bad in (True, "abc", float("nan")):
            with pytest.raises(ValueError):
                coerce(prop, bad)
        assert present(prop, [held(prop, value_number=Decimal("2"))]) == 2
        assert isinstance(present(prop, [held(prop, value_number=Decimal("2"))]), int)
        assert present(prop, [held(prop, value_number=Decimal("2.5"))]) == 2.5

    def test_boolean(self, define):
        prop = define("done", T.BOOLEAN)
        assert coerce(prop, False) == [False]
        with pytest.raises(ValueError):
            coerce(prop, "true")

    def test_date(self, define):
        prop = define("when", T.DATE)
        assert coerce(prop, "2026-01-02") == [date(2026, 1, 2)]
        with pytest.raises(ValueError):
            coerce(prop, "02/01/2026")
        assert present(prop, [held(prop, value_date=date(2026, 1, 2))]) == "2026-01-02"

    def test_datetime_is_stored_utc(self, define):
        prop = define("at", T.DATETIME)
        assert coerce(prop, "2026-01-01T10:00:00+02:00") == [datetime(2026, 1, 1, 8, 0, tzinfo=dt_timezone.utc)]
        assert coerce(prop, "2026-01-01T10:00:00Z") == [datetime(2026, 1, 1, 10, 0, tzinfo=dt_timezone.utc)]
        with pytest.raises(ValueError):
            coerce(prop, "2026-01-01T10:00:00")
        value = held(prop, value_datetime=datetime(2026, 1, 1, 8, 0, tzinfo=dt_timezone.utc))
        assert present(prop, [value]) == "2026-01-01T08:00:00Z"

    def test_url(self, define):
        prop = define("pr", T.URL)
        assert coerce(prop, "https://github.com/x/y/pull/1") == ["https://github.com/x/y/pull/1"]
        for bad in ("ftp://x", "github.com/x", "https://"):
            with pytest.raises(ValueError):
                coerce(prop, bad)

    def test_choice(self, define):
        prop = define("repo", T.CHOICE, options=[{"id": "plane", "label": "Plane", "disabled": False}])
        assert coerce(prop, "plane") == ["plane"]
        with pytest.raises(ValueError):
            coerce(prop, "nope")

    def test_member(self, define, project, create_user, workspace):
        prop = define("owner", T.MEMBER)
        assert coerce(prop, str(create_user.id)) == [create_user.id]
        outsider = User.objects.create(email="out@plane.so", username="out")
        WorkspaceMember.objects.create(workspace=workspace, member=outsider, role=15)
        for bad in (str(outsider.id), "not-a-uuid"):
            with pytest.raises(ValueError):
                coerce(prop, bad)

    def test_multiple_takes_a_list(self, define):
        options = [{"id": i, "label": i.upper(), "disabled": False} for i in ("a", "b")]
        prop = define("tags", T.CHOICE, options=options, multiple=True)
        assert coerce(prop, ["a", "a", "b"]) == ["a", "b"]
        assert coerce(prop, None) == []
        assert coerce(prop, []) == []
        with pytest.raises(ValueError):
            coerce(prop, "a")
        assert present(prop, []) == []
        assert present(define("one", T.TEXT), []) is None

    def test_key_stays_reserved_after_delete(self, define):
        define("repo", T.TEXT).delete()
        with pytest.raises(IntegrityError), transaction.atomic():
            define("repo", T.TEXT)


def member_client(clients, project, role, name="member"):
    """clients.anon as a fresh project member with role."""
    user = User.objects.create(email=f"{name}@plane.so", username=name, display_name=name)
    WorkspaceMember.objects.create(workspace=project.workspace, member=user, role=15)
    ProjectMember.objects.create(project=project, member=user, role=role, is_active=True)
    token = APIToken.objects.create(user=user, label=name, token=f"token-{name}").token
    clients.anon.credentials(HTTP_X_API_KEY=token)
    return clients.anon


def props_url(project, tail=""):
    return f"/api/v1/workspaces/{project.workspace.slug}/projects/{project.id}/properties/{tail}"


@pytest.mark.contract
@pytest.mark.django_db
class TestDefinitions:
    def create(self, client, project, **body):
        return client.post(props_url(project), body, format="json")

    def test_admin_creates_a_choice_with_derived_option_ids(self, clients, project):
        response = self.create(
            clients.api_key,
            project,
            name="Waiting on",
            key="waiting_on",
            type="choice",
            options=[{"label": "Needs owner"}, {"label": "Needs-owner!"}, {"id": "agent", "label": "Agent"}],
        )
        assert response.status_code == status.HTTP_201_CREATED, response.json()
        body = response.json()
        assert [o["id"] for o in body["options"]] == ["needs_owner", "needs_owner_2", "agent"]
        assert all(o["disabled"] is False for o in body["options"])
        assert body["write_role"] == 15 and body["visible"] is True and body["multiple"] is False
        assert set(body) >= {"id", "name", "key", "type", "description", "sort_order", "created_at", "updated_at"}

    def test_members_read_but_only_admins_write(self, clients, project):
        prop = self.create(clients.api_key, project, name="Repo", key="repo", type="text").json()
        member = member_client(clients, project, 15)
        assert member.get(props_url(project)).status_code == status.HTTP_200_OK
        assert [p["key"] for p in member.get(props_url(project)).json()] == ["repo"]
        assert member.get(props_url(project, f"{prop['id']}/")).status_code == status.HTTP_200_OK
        assert self.create(member, project, name="X", key="x", type="text").status_code == 403
        assert member.patch(props_url(project, f"{prop['id']}/"), {"name": "Y"}, format="json").status_code == 403
        assert member.delete(props_url(project, f"{prop['id']}/")).status_code == 403

    def test_non_members_cannot_read(self, clients, project, workspace):
        user = User.objects.create(email="guest@plane.so", username="guest")
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
        clients.anon.credentials(HTTP_X_API_KEY=APIToken.objects.create(user=user, label="g", token="token-g").token)
        assert clients.anon.get(props_url(project)).status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize(
        "body",
        [
            {"name": "Bad", "key": "Bad Key", "type": "text"},
            {"name": "Bad", "key": "bad", "type": "nope"},
            {"name": "Bad", "key": "bad", "type": "text", "options": [{"label": "A"}]},
            {
                "name": "Bad",
                "key": "bad",
                "type": "choice",
                "options": [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}],
            },
            {"name": "Bad", "key": "bad", "type": "choice", "options": [{"id": "A B", "label": "A"}]},
            {"name": "Bad", "key": "bad", "type": "choice", "options": [{"label": ""}]},
            {"name": "Bad", "key": "bad", "type": "text", "write_role": 10},
        ],
    )
    def test_create_validates(self, clients, project, body):
        assert self.create(clients.api_key, project, **body).status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_and_deleted_keys_are_refused(self, clients, project):
        prop = self.create(clients.api_key, project, name="Repo", key="repo", type="text").json()
        assert self.create(clients.api_key, project, name="Repo", key="repo", type="text").status_code == 400
        assert clients.api_key.delete(props_url(project, f"{prop['id']}/")).status_code == 204
        assert clients.api_key.get(props_url(project)).json() == []
        assert clients.api_key.get(props_url(project, f"{prop['id']}/")).status_code == 404
        assert self.create(clients.api_key, project, name="Repo", key="repo", type="text").status_code == 400

    def test_type_and_key_cannot_change(self, clients, project):
        prop = self.create(clients.api_key, project, name="Repo", key="repo", type="text").json()
        url = props_url(project, f"{prop['id']}/")
        assert clients.api_key.patch(url, {"type": "number"}, format="json").status_code == 400
        assert clients.api_key.patch(url, {"key": "other"}, format="json").status_code == 400
        assert clients.api_key.patch(url, {"key": "repo", "name": "Repository"}, format="json").status_code == 200
        response = clients.api_key.patch(url, {"visible": False, "sort_order": 1, "write_role": 20}, format="json")
        assert response.status_code == 200
        assert (response.json()["visible"], response.json()["write_role"]) == (False, 20)

    def test_options_rename_disable_and_held_removal(self, clients, project, define):
        prop = define(
            "repo",
            T.CHOICE,
            options=[
                {"id": "plane", "label": "Plane", "disabled": False},
                {"id": "mcp", "label": "MCP", "disabled": False},
            ],
        )
        CustomValue.objects.create(
            issue=make_issue(project, "A"),
            property=prop,
            value_text="plane",
            project=project,
            workspace=project.workspace,
        )
        url = props_url(project, f"{prop.id}/")
        renamed = [{"id": "plane", "label": "Plane fork", "disabled": True}, {"id": "mcp", "label": "MCP"}]
        response = clients.api_key.patch(url, {"options": renamed}, format="json")
        assert response.status_code == 200, response.json()
        assert response.json()["options"][0] == {"id": "plane", "label": "Plane fork", "disabled": True}
        response = clients.api_key.patch(url, {"options": [{"id": "mcp", "label": "MCP"}]}, format="json")
        assert response.status_code == 400
        assert "1 work item" in str(response.json())
        assert (
            clients.api_key.patch(url, {"options": [{"id": "plane", "label": "P"}]}, format="json").status_code == 200
        )

    def test_multiple_off_is_refused_while_an_item_holds_several(self, clients, project, define):
        options = [{"id": i, "label": i, "disabled": False} for i in ("a", "b")]
        prop = define("tags", T.CHOICE, options=options, multiple=True)
        issue = make_issue(project, "A")
        for i, value in enumerate(("a", "b")):
            CustomValue.objects.create(
                issue=issue, property=prop, value_text=value, position=i, project=project, workspace=project.workspace
            )
        url = props_url(project, f"{prop.id}/")
        assert clients.api_key.patch(url, {"multiple": False}, format="json").status_code == 400
        CustomValue.objects.filter(value_text="b").delete()
        assert clients.api_key.patch(url, {"multiple": False}, format="json").status_code == 200

    def test_another_projects_property_is_not_found(self, clients, project, workspace, create_user):
        other = make_project(workspace, create_user, "Other", "OT")
        prop = CustomProperty.objects.create(project=other, workspace=workspace, key="x", name="X", type="text")
        assert clients.api_key.get(props_url(project, f"{prop.id}/")).status_code == 404


@pytest.fixture
def webhook():
    with mock.patch("plane.ext.properties.webhook_activity.delay") as delay:
        yield delay


@pytest.fixture
def item(project):
    return make_issue(project, "Ship it")


@pytest.fixture
def fields(define):
    """repo (choice), count (number), tags (multi choice), owner (member), hidden note (text)."""
    options = [{"id": i, "label": i.title(), "disabled": False} for i in ("plane", "mcp")]
    return SimpleFields(
        repo=define("repo", T.CHOICE, options=options),
        count=define("count", T.NUMBER),
        tags=define("tags", T.CHOICE, options=options, multiple=True),
        owner=define("owner", T.MEMBER),
        note=define("note", T.TEXT, visible=False),
    )


class SimpleFields(dict):
    __getattr__ = dict.__getitem__


EMPTY = {"repo": None, "count": None, "tags": [], "owner": None, "note": None}


def item_url(issue, items="work-items"):
    return f"/api/v1/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/{items}/{issue.id}/"


def list_url(project, items="work-items"):
    return f"/api/v1/workspaces/{project.workspace.slug}/projects/{project.id}/{items}/"


def rows(issue):
    return IssueActivity.objects.filter(issue=issue, field="custom_fields").order_by("created_at")


@pytest.mark.contract
@pytest.mark.django_db
class TestValues:
    def patch(self, client, issue, body):
        return client.patch(item_url(issue), body, format="json")

    def test_read_has_every_live_property_hidden_included(self, clients, item, fields, define):
        define("gone", T.TEXT).delete()
        body = clients.api_key.get(item_url(item)).json()
        assert body["custom_fields"] == EMPTY

    def test_set_reads_back_with_activity_and_one_webhook(
        self, clients, item, fields, webhook, create_user, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = self.patch(
                clients.api_key, item, {"custom_fields": {"repo": "plane", "count": 3, "owner": str(create_user.id)}}
            )
        assert response.status_code == 200, response.json()
        expected = {**EMPTY, "repo": "plane", "count": 3, "owner": str(create_user.id)}
        assert response.json()["custom_fields"] == expected
        assert clients.api_key.get(item_url(item)).json()["custom_fields"] == expected
        activity = {row.comment: (row.old_value, row.new_value) for row in rows(item)}
        assert activity == {
            "updated Repo": (None, "Plane"),
            "updated Count": (None, "3"),
            "updated Owner": (None, create_user.display_name),
        }
        assert all(row.actor_id == create_user.id for row in rows(item))
        webhook.assert_called_once()
        call = webhook.call_args.kwargs
        assert (call["event"], call["field"], call["event_id"]) == ("issue", "custom_fields", str(item.id))
        assert call["old_value"] == {"repo": None, "count": None, "owner": None}
        assert call["new_value"] == {"repo": "plane", "count": 3, "owner": str(create_user.id)}

    def test_a_held_number_or_boolean_changes(self, clients, item, fields, define):
        define("done", T.BOOLEAN)
        assert self.patch(clients.api_key, item, {"custom_fields": {"count": 2, "done": True}}).status_code == 200
        response = self.patch(clients.api_key, item, {"custom_fields": {"count": 3.5, "done": False}})
        assert response.status_code == 200, response.json()
        assert (response.json()["custom_fields"]["count"], response.json()["custom_fields"]["done"]) == (3.5, False)

    def test_same_values_write_nothing(self, clients, item, fields, webhook):
        self.patch(clients.api_key, item, {"custom_fields": {"repo": "plane"}})
        webhook.reset_mock()
        assert self.patch(clients.api_key, item, {"custom_fields": {"repo": "plane"}}).status_code == 200
        assert rows(item).count() == 1
        webhook.assert_not_called()

    def test_null_clears_and_lists_replace(self, clients, item, fields, webhook):
        self.patch(clients.api_key, item, {"custom_fields": {"repo": "plane", "tags": ["plane", "mcp"]}})
        response = self.patch(clients.api_key, item, {"custom_fields": {"repo": None, "tags": ["mcp"]}})
        assert response.json()["custom_fields"]["repo"] is None
        assert response.json()["custom_fields"]["tags"] == ["mcp"]
        assert CustomValue.objects.filter(issue=item).count() == 1
        assert rows(item).filter(comment="updated Tags").last().old_value == "Plane, Mcp"

    def test_an_invalid_value_writes_nothing_else(self, clients, item, fields, webhook):
        response = self.patch(
            clients.api_key, item, {"name": "Renamed", "custom_fields": {"repo": "plane", "count": "abc", "nope": 1}}
        )
        assert response.status_code == 400
        assert set(response.json()["custom_fields"]) == {"count", "nope"}
        item.refresh_from_db()
        assert item.name == "Ship it"
        assert not CustomValue.objects.filter(issue=item).exists()
        webhook.assert_not_called()

    def test_an_upstream_error_writes_no_values(self, clients, item, fields):
        response = self.patch(clients.api_key, item, {"priority": "bogus", "custom_fields": {"repo": "plane"}})
        assert response.status_code == 400
        assert not CustomValue.objects.filter(issue=item).exists()

    @pytest.mark.parametrize("payload", [["repo"], "repo"])
    def test_custom_fields_must_be_an_object(self, clients, item, fields, payload):
        assert self.patch(clients.api_key, item, {"custom_fields": payload}).status_code == 400

    def test_a_deleted_property_cannot_be_written(self, clients, item, fields):
        fields.note.delete()
        response = self.patch(clients.api_key, item, {"custom_fields": {"note": "x"}})
        assert response.status_code == 400 and "note" in response.json()["custom_fields"]

    def test_create_with_values(self, clients, project, fields, webhook, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            response = clients.api_key.post(
                list_url(project), {"name": "New", "custom_fields": {"count": 2.5}}, format="json"
            )
        assert response.status_code == 201, response.json()
        assert response.json()["custom_fields"]["count"] == 2.5
        webhook.assert_called_once()

    def test_create_with_a_bad_value_creates_nothing(self, clients, project, fields):
        response = clients.api_key.post(list_url(project), {"name": "New", "custom_fields": {"nope": 1}}, format="json")
        assert response.status_code == 400
        assert not project.project_issue.filter(name="New").exists()

    def test_write_role(self, clients, project, item, define):
        define("verdict", T.TEXT, write_role=20)
        define("free", T.TEXT, write_role=5)
        member = member_client(clients, project, 15)
        response = member.patch(item_url(item), {"custom_fields": {"verdict": "pass"}}, format="json")
        assert response.status_code == 400 and "verdict" in response.json()["custom_fields"]
        assert member.patch(item_url(item), {"custom_fields": {"free": "x"}}, format="json").status_code == 200
        assert self.patch(clients.api_key, item, {"custom_fields": {"verdict": "pass"}}).status_code == 200

    def test_a_disabled_option_stays_but_cannot_be_newly_set(self, clients, project, item, fields):
        self.patch(clients.api_key, item, {"custom_fields": {"repo": "mcp", "tags": ["mcp"]}})
        for prop in (fields.repo, fields.tags):
            prop.options = [{**o, "disabled": o["id"] == "mcp"} for o in prop.options]
            prop.save()
        assert clients.api_key.get(item_url(item)).json()["custom_fields"]["repo"] == "mcp"
        assert (
            self.patch(clients.api_key, item, {"custom_fields": {"repo": "mcp", "tags": ["plane", "mcp"]}}).status_code
            == 200
        )
        other = make_issue(project, "Other")
        assert self.patch(clients.api_key, other, {"custom_fields": {"repo": "mcp"}}).status_code == 400

    def test_a_member_who_left_survives_a_resend(self, clients, project, item, fields):
        member_client(clients, project, 15, name="leaver")
        leaver = User.objects.get(username="leaver")
        self.patch(clients.api_key, item, {"custom_fields": {"owner": str(leaver.id)}})
        ProjectMember.objects.filter(member=leaver).update(is_active=False)
        assert self.patch(clients.api_key, item, {"custom_fields": {"owner": str(leaver.id)}}).status_code == 200
        other = make_issue(project, "Other")
        assert self.patch(clients.api_key, other, {"custom_fields": {"owner": str(leaver.id)}}).status_code == 400

    def test_fields_selects_custom_fields(self, clients, item, fields):
        url = item_url(item)
        assert "custom_fields" not in clients.api_key.get(url + "?fields=id,name").json()
        assert set(clients.api_key.get(url + "?fields=custom_fields").json()) == {"id", "custom_fields"}
        assert set(clients.api_key.get(url + "?fields=name,custom_fields").json()) == {"name", "custom_fields"}
        assert set(clients.api_key.get(url + "?fields=custom_fields,steps").json()) >= {"steps", "custom_fields"}

    @pytest.mark.parametrize("items", ["work-items", "issues"])
    def test_list_and_by_identifier_reads(self, clients, project, item, fields, items):
        self.patch(clients.api_key, item, {"custom_fields": {"count": 7}})
        results = clients.api_key.get(list_url(project, items)).json()["results"]
        assert [r["custom_fields"]["count"] for r in results] == [7]
        by_id = f"/api/v1/workspaces/{project.workspace.slug}/{items}/{project.identifier}-{item.sequence_id}/"
        assert clients.api_key.get(by_id).json()["custom_fields"]["count"] == 7
        listed = clients.api_key.get(list_url(project, items) + "?fields=name").json()["results"]
        assert "custom_fields" not in listed[0]

    def test_a_moved_item_hides_its_old_values(self, clients, project, item, fields, workspace, create_user):
        self.patch(clients.api_key, item, {"custom_fields": {"count": 1}})
        other = make_project(workspace, create_user, "Other", "OT")
        Issue.objects.filter(pk=item.pk).update(project=other)
        item.refresh_from_db()
        assert clients.api_key.get(item_url(item)).json()["custom_fields"] == {}
        Issue.objects.filter(pk=item.pk).update(project=project)
        item.refresh_from_db()
        assert clients.api_key.get(item_url(item)).json()["custom_fields"]["count"] == 1
