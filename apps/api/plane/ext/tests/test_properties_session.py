# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid
from unittest import mock

import pytest
from django.urls import resolve
from rest_framework import status
from rest_framework.test import APIClient

from plane.authentication.session import BaseSessionAuthentication
from plane.db.models import Issue, IssueActivity, ProjectMember, User, WorkspaceMember
from plane.ext.models import CustomProperty
from plane.ext.properties import (
    ItemCustomFieldsEndpoint,
    SessionPropertyDetailEndpoint,
    SessionPropertyListCreateEndpoint,
)
from plane.ext.tests.conftest import make_issue, make_project

T = CustomProperty.Type


def view_of(path):
    func = resolve(path).func
    return getattr(func, "__wrapped__", func).cls


@pytest.mark.unit
def test_session_routes_resolve_to_session_views():
    base = f"/api/workspaces/acme/projects/{uuid.uuid4()}/"
    assert view_of(base + "properties/") is SessionPropertyListCreateEndpoint
    assert view_of(base + f"properties/{uuid.uuid4()}/") is SessionPropertyDetailEndpoint
    assert view_of(base + f"issues/{uuid.uuid4()}/custom-fields/") is ItemCustomFieldsEndpoint
    for view in (SessionPropertyListCreateEndpoint, SessionPropertyDetailEndpoint, ItemCustomFieldsEndpoint):
        assert view.authentication_classes == [BaseSessionAuthentication]


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Props", "PS")


@pytest.fixture
def other_project(db, workspace, create_user):
    return make_project(workspace, create_user, "Other", "OT")


@pytest.fixture
def define(project, create_user):
    def define(key, type, **fields):
        fields.setdefault("name", key.title())
        return CustomProperty.objects.create(
            project=project, workspace=project.workspace, key=key, type=type, created_by=create_user, **fields
        )

    return define


@pytest.fixture
def item(project):
    return make_issue(project, "Ship it")


@pytest.fixture
def admin(clients):
    with mock.patch("plane.ext.properties.webhook_activity.delay"):
        yield clients.session


@pytest.fixture
def as_role(project):
    """A session client for a fresh workspace user with this project role (None: not a member)."""

    def as_role(role, name="someone"):
        user = User.objects.create(email=f"{name}@plane.so", username=name, display_name=name)
        WorkspaceMember.objects.create(workspace=project.workspace, member=user, role=15)
        if role is not None:
            ProjectMember.objects.create(project=project, member=user, role=role, is_active=True)
        client = APIClient()
        client.force_authenticate(user=user)
        client.raise_request_exception = False
        client.user = user
        return client

    with mock.patch("plane.ext.properties.webhook_activity.delay"):
        yield as_role


def props_url(project, tail=""):
    return f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/properties/{tail}"


def fields_url(issue, project=None):
    project = project or issue.project
    return f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/issues/{issue.id}/custom-fields/"


def rows(issue):
    return IssueActivity.objects.filter(issue=issue, field="custom_fields").order_by("created_at")


@pytest.mark.contract
@pytest.mark.django_db
class TestSessionDefinitions:
    def test_admin_crud_over_session(self, admin, project):
        created = admin.post(
            props_url(project),
            {"name": "Repo", "key": "repo", "type": "choice", "options": [{"label": "plane"}]},
            format="json",
        )
        assert created.status_code == status.HTTP_201_CREATED
        prop_id = created.json()["id"]
        moved = admin.patch(props_url(project, f"{prop_id}/"), {"sort_order": 5}, format="json")
        assert moved.status_code == status.HTTP_200_OK
        assert moved.json()["sort_order"] == 5
        assert admin.delete(props_url(project, f"{prop_id}/")).status_code == status.HTTP_204_NO_CONTENT
        assert admin.get(props_url(project)).json() == []

    def test_member_cannot_define(self, as_role, project):
        member = as_role(15)
        response = member.post(props_url(project), {"name": "Repo", "key": "repo", "type": "text"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == {"error": "Only project admins can change properties"}


@pytest.mark.contract
@pytest.mark.django_db
class TestItemFields:
    @pytest.fixture
    def props(self, define, item, admin):
        customer = define("customer", T.TEXT)
        define("verdict", T.BOOLEAN, write_role=20)
        define("secret", T.TEXT, visible=False)
        define("points", T.NUMBER)
        assert admin.patch(fields_url(item), {"customer": "Acme"}, format="json").status_code == 200
        return customer

    def test_get_values_and_can_write(self, as_role, item, props):
        body = as_role(15).get(fields_url(item)).json()
        assert body["values"] == {"customer": "Acme", "verdict": None, "secret": None, "points": None}
        assert body["can_write"] == {"customer": True, "verdict": False, "secret": True, "points": True}

    def test_patch_all_or_nothing(self, admin, item, props):
        before = rows(item).count()
        response = admin.patch(fields_url(item), {"customer": "B", "points": "x"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["custom_fields"]["points"].startswith("expects a number")
        assert admin.get(fields_url(item)).json()["values"]["customer"] == "Acme"
        assert rows(item).count() == before

    def test_patch_writes_and_clears(self, admin, item, props):
        response = admin.patch(fields_url(item), {"customer": "B"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["values"]["customer"] == "B"
        last = rows(item).last()
        assert (last.comment, last.old_value, last.new_value) == ("updated Customer", "Acme", "B")
        cleared = admin.patch(fields_url(item), {"customer": None}, format="json")
        assert cleared.json()["values"]["customer"] is None
        assert rows(item).last().new_value is None

    def test_role_below_write_role(self, as_role, item, props):
        response = as_role(15).patch(fields_url(item), {"verdict": True}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "needs project role Admin" in response.json()["custom_fields"]["verdict"]

    def test_not_member_and_wrong_project(self, as_role, admin, item, other_project, props):
        assert as_role(None).get(fields_url(item)).status_code == status.HTTP_403_FORBIDDEN
        assert admin.get(fields_url(item, other_project)).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.contract
@pytest.mark.django_db
def test_disabled_option_survives_resend(admin, define, item, project):
    options = [{"id": i, "label": i.upper(), "disabled": False} for i in ("a", "b", "c")]
    tags = define("tags", T.CHOICE, options=options, multiple=True)
    assert admin.patch(fields_url(item), {"tags": ["a", "b"]}, format="json").status_code == 200
    disabled = [{**o, "disabled": o["id"] in ("b", "c")} for o in options]
    assert admin.patch(props_url(project, f"{tags.id}/"), {"options": disabled}, format="json").status_code == 200
    kept = admin.patch(fields_url(item), {"tags": ["b"]}, format="json")
    assert kept.status_code == status.HTTP_200_OK
    assert kept.json()["values"]["tags"] == ["b"]
    assert admin.patch(fields_url(item), {"tags": ["b", "c"]}, format="json").status_code == 400


@pytest.mark.contract
@pytest.mark.django_db
class TestGuests:
    def test_guest_can_write_guest_property(self, as_role, define, item, project):
        define("mood", T.TEXT, write_role=5)
        define("customer", T.TEXT)
        project.guest_view_all_features = True
        project.save()
        guest = as_role(5)
        assert guest.patch(fields_url(item), {"mood": "ok"}, format="json").status_code == status.HTTP_200_OK
        assert guest.get(fields_url(item)).json()["can_write"] == {"mood": True, "customer": False}
        assert guest.patch(fields_url(item), {"customer": "x"}, format="json").status_code == 400

    def test_guest_cannot_reach_an_item_they_cannot_see(self, as_role, define, item, project):
        define("mood", T.TEXT, write_role=5)
        project.guest_view_all_features = False
        project.save()
        guest = as_role(5)
        assert guest.get(fields_url(item)).status_code == status.HTTP_404_NOT_FOUND
        own = make_issue(project, "Mine")
        Issue.objects.filter(pk=own.pk).update(created_by=guest.user)  # save() takes created_by from the request
        assert guest.patch(fields_url(own), {"mood": "ok"}, format="json").status_code == status.HTTP_200_OK
