# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import base64
import json
from unittest import mock

import pytest
import requests
from rest_framework import status

from plane.db.models import Page, Project, ProjectMember, ProjectPage, User, WorkspaceMember
from plane.db.models.api import APIToken

# the fields plane_sdk's Page model reads
SDK_PAGE_FIELDS = {
    "id",
    "name",
    "description_stripped",
    "description_html",
    "created_at",
    "updated_at",
    "owned_by",
    "workspace",
    "projects",
    "access",
    "is_locked",
    "archived_at",
    "parent_id",
    "collection_id",
    "page_collection_id",
}


@pytest.fixture(autouse=True)
def no_tasks():
    with (
        mock.patch("plane.ext.pages.page_transaction.delay") as transaction_task,
        mock.patch("plane.ext.pages.track_page_version.delay") as version_task,
    ):
        yield {"transaction": transaction_task, "version": version_task}


@pytest.fixture(autouse=True)
def live_settings(settings, monkeypatch):
    settings.LIVE_URL = "http://live.test/live/"
    monkeypatch.setenv("LIVE_SERVER_SECRET_KEY", "test-secret")


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Pages", identifier="PG", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


def make_page(project, owner, name="Doc", html="<p>old</p>", **fields):
    page = Page.objects.create(workspace=project.workspace, owned_by=owner, name=name, description_html=html, **fields)
    ProjectPage.objects.create(workspace=project.workspace, project=project, page=page)
    return page


def other_member(project, role, email="other@plane.so"):
    user = User.objects.create(email=email, username=email.split("@")[0])
    WorkspaceMember.objects.create(workspace=project.workspace, member=user, role=role)
    ProjectMember.objects.create(project=project, member=user, role=role, is_active=True)
    token = APIToken.objects.create(user=user, label="other", token=f"token-{user.username}")
    return user, token.token


def live_reply(html="<p>new</p>", binary=b"\x01\x02"):
    response = mock.Mock(status_code=200)
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "description_binary": base64.b64encode(binary).decode(),
        "description_html": html,
        "description_json": {"type": "doc"},
        "loaded": False,
    }
    return response


def pages_url(project):
    return f"/api/v1/workspaces/{project.workspace.slug}/projects/{project.id}/pages/"


def page_url(project, page):
    return f"{pages_url(project)}{page.id}/"


@pytest.mark.contract
@pytest.mark.django_db
class TestCreateAndRead:
    def test_create_returns_the_sdk_shape(self, api_key_client, project, create_user, no_tasks):
        response = api_key_client.post(
            pages_url(project), {"name": "Spec", "description_html": "<p>hello</p>"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert SDK_PAGE_FIELDS <= set(response.data)
        assert "description_binary" not in response.data
        assert response.data["projects"] == [str(project.id)]
        page = Page.objects.get(pk=response.data["id"])
        assert page.description_html == "<p>hello</p>"
        assert page.description_binary is None
        assert page.owned_by_id == create_user.id
        no_tasks["transaction"].assert_called_once()

    def test_create_requires_name_and_html(self, api_key_client, project):
        response = api_key_client.post(pages_url(project), {"name": "Spec"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_sanitises_html(self, api_key_client, project):
        response = api_key_client.post(
            pages_url(project),
            {"name": "Spec", "description_html": "<p>hi</p><script>alert(1)</script>"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "script" not in Page.objects.get(pk=response.data["id"]).description_html

    def test_create_child_page(self, api_key_client, project, create_user):
        parent = make_page(project, create_user)
        response = api_key_client.post(
            pages_url(project),
            {"name": "Child", "description_html": "<p>c</p>", "parent_id": str(parent.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["parent_id"] == str(parent.id)

        listed = api_key_client.get(pages_url(project)).data["results"]
        assert {p["name"] for p in listed} == {"Doc", "Child"}

    def test_parent_from_another_project_is_refused(self, api_key_client, project, workspace, create_user):
        elsewhere = Project.objects.create(name="Else", identifier="EL", workspace=workspace)
        parent = make_page(elsewhere, create_user)
        response = api_key_client.post(
            pages_url(project),
            {"name": "Child", "description_html": "<p>c</p>", "parent_id": str(parent.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve_includes_html(self, api_key_client, project, create_user):
        page = make_page(project, create_user)
        response = api_key_client.get(page_url(project, page))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["description_html"] == "<p>old</p>"
        assert response.data["description_stripped"] == "old"

    def test_page_of_another_project_is_not_found(self, api_key_client, project, workspace, create_user):
        elsewhere = Project.objects.create(name="Else", identifier="EL", workspace=workspace)
        page = make_page(elsewhere, create_user)
        response = api_key_client.get(page_url(project, page))
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_someone_elses_private_page_is_hidden(self, api_client, project, create_user):
        page = make_page(project, create_user, access=Page.PRIVATE_ACCESS)
        _, token = other_member(project, role=15)
        api_client.credentials(HTTP_X_API_KEY=token)
        assert api_client.get(page_url(project, page)).status_code == status.HTTP_403_FORBIDDEN
        assert api_client.get(pages_url(project)).data["results"] == []

    def test_guest_sees_only_own_pages(self, api_client, project, create_user):
        make_page(project, create_user)
        _, token = other_member(project, role=5)
        api_client.credentials(HTTP_X_API_KEY=token)
        assert api_client.get(pages_url(project)).data["results"] == []


@pytest.mark.contract
@pytest.mark.django_db
class TestUpdate:
    def test_content_goes_through_live(self, api_key_client, project, create_user, no_tasks):
        page = make_page(project, create_user, description_binary=b"stored")
        with mock.patch("plane.ext.pages.requests.post", return_value=live_reply()) as post:
            response = api_key_client.put(page_url(project, page), {"description_html": "<p>new</p>"}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data

        url = post.call_args.args[0]
        assert url == f"http://live.test/live/squadron/pages/{page.id}/content/"
        headers = post.call_args.kwargs["headers"]
        assert headers["live-server-secret-key"] == "test-secret"
        assert headers["content-type"] == "application/vnd.squadron.page-content+json"
        sent = json.loads(post.call_args.kwargs["data"])
        assert sent == {
            "description_html": "<p>new</p>",
            "name": None,
            "description_binary": base64.b64encode(b"stored").decode(),
        }

        page.refresh_from_db()
        assert bytes(page.description_binary) == b"\x01\x02"
        assert page.description_html == "<p>new</p>"
        assert page.description_json == {"type": "doc"}
        assert response.data["description_html"] == "<p>new</p>"
        no_tasks["version"].assert_called_once()
        no_tasks["transaction"].assert_called_once()

    def test_rename_reaches_the_editor_title(self, api_key_client, project, create_user):
        page = make_page(project, create_user)
        with mock.patch("plane.ext.pages.requests.post", return_value=live_reply("<p>old</p>")) as post:
            response = api_key_client.put(page_url(project, page), {"name": "Renamed"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert json.loads(post.call_args.kwargs["data"])["name"] == "Renamed"
        assert Page.objects.get(pk=page.id).name == "Renamed"

    def test_other_fields_skip_live(self, api_key_client, project, create_user):
        page = make_page(project, create_user)
        with mock.patch("plane.ext.pages.requests.post") as post:
            response = api_key_client.patch(page_url(project, page), {"color": "#123456"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        post.assert_not_called()
        assert Page.objects.get(pk=page.id).color == "#123456"

    def test_live_down_writes_nothing(self, api_key_client, project, create_user):
        page = make_page(project, create_user)
        with mock.patch("plane.ext.pages.requests.post", side_effect=requests.ConnectionError("down")):
            response = api_key_client.put(
                page_url(project, page), {"name": "New", "description_html": "<p>new</p>"}, format="json"
            )
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        page.refresh_from_db()
        assert (page.name, page.description_html) == ("Doc", "<p>old</p>")

    def test_live_unconfigured_is_502(self, api_key_client, project, create_user, settings):
        settings.LIVE_URL = None
        page = make_page(project, create_user)
        response = api_key_client.put(page_url(project, page), {"description_html": "<p>new</p>"}, format="json")
        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @pytest.mark.parametrize("fields", [{"is_locked": True}, {"archived_at": "2026-01-01"}])
    def test_locked_or_archived_is_refused(self, api_key_client, project, create_user, fields):
        page = make_page(project, create_user, **fields)
        with mock.patch("plane.ext.pages.requests.post") as post:
            response = api_key_client.put(page_url(project, page), {"description_html": "<p>x</p>"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        post.assert_not_called()

    def test_only_owner_changes_access(self, api_client, project, create_user):
        page = make_page(project, create_user)
        _, token = other_member(project, role=15)
        api_client.credentials(HTTP_X_API_KEY=token)
        response = api_client.patch(page_url(project, page), {"access": 1}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_guest_cannot_update(self, api_client, project, create_user):
        page = make_page(project, create_user)
        _, token = other_member(project, role=5)
        api_client.credentials(HTTP_X_API_KEY=token)
        response = api_client.patch(page_url(project, page), {"color": "#000000"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
@pytest.mark.django_db
class TestArchiveAndDelete:
    def test_delete_requires_archive(self, api_key_client, project, create_user):
        page = make_page(project, create_user)
        assert api_key_client.delete(page_url(project, page)).status_code == status.HTTP_400_BAD_REQUEST

        assert api_key_client.post(f"{page_url(project, page)}archive/").status_code == status.HTTP_200_OK
        assert Page.objects.get(pk=page.id).archived_at is not None
        assert api_key_client.delete(page_url(project, page)).status_code == status.HTTP_204_NO_CONTENT
        assert not Page.objects.filter(pk=page.id).exists()

    def test_unarchive(self, api_key_client, project, create_user):
        page = make_page(project, create_user)
        api_key_client.post(f"{page_url(project, page)}archive/")
        assert api_key_client.delete(f"{page_url(project, page)}archive/").status_code == status.HTTP_204_NO_CONTENT
        assert Page.objects.get(pk=page.id).archived_at is None

    def test_requires_an_api_key(self, api_client, project):
        assert api_client.get(pages_url(project)).status_code == status.HTTP_401_UNAUTHORIZED
