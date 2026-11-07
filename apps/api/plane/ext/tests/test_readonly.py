# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid

import pytest
from rest_framework import status

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.db.models import Issue, IssueComment
from plane.ext.readonly import SETTING, install
from plane.ext.tests.conftest import make_issue, make_project


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Read only", "RO")


@pytest.fixture
def issue(project):
    return make_issue(project, "Untouched")


@pytest.fixture
def v1(workspace, project):
    return lambda tail: f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/{tail}"


@pytest.fixture
def client(api_key_client, monkeypatch):
    monkeypatch.setattr("celery.app.task.Task.delay", lambda *a, **k: None)
    api_key_client.raise_request_exception = False
    return api_key_client


@pytest.fixture
def read_only(monkeypatch, create_user):
    monkeypatch.setenv(SETTING, f" {uuid.uuid4()} , {str(create_user.id).upper()} ")


def test_installed_at_app_start():
    assert getattr(APIKeyAuthentication.authenticate, "squadron_read_only", False)
    install()  # a second install doesn't wrap twice
    assert getattr(APIKeyAuthentication.authenticate, "squadron_read_only", False)


@pytest.mark.django_db
class TestReadOnlyUser:
    def test_reads(self, client, read_only, v1, issue):
        assert client.get(v1("work-items/")).status_code == status.HTTP_200_OK
        assert client.get(v1(f"work-items/{issue.id}/")).status_code == status.HTTP_200_OK
        assert client.get(v1(f"work-items/{issue.id}/comments/")).status_code == status.HTTP_200_OK

    def test_cannot_comment(self, client, read_only, v1, issue):
        response = client.post(v1(f"work-items/{issue.id}/comments/"), {"comment_html": "<p>x</p>"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == {"detail": "This identity is read-only."}
        assert not IssueComment.objects.filter(issue=issue).exists()

    def test_cannot_create_update_or_delete(self, client, read_only, v1, issue):
        assert client.post(v1("work-items/"), {"name": "New"}, format="json").status_code == 403
        assert client.patch(v1(f"work-items/{issue.id}/"), {"name": "Changed"}, format="json").status_code == 403
        assert client.put(v1(f"work-items/{issue.id}/"), {"name": "Changed"}, format="json").status_code == 403
        assert client.delete(v1(f"work-items/{issue.id}/")).status_code == 403
        assert list(Issue.objects.filter(project=issue.project).values_list("name", flat=True)) == ["Untouched"]


@pytest.mark.django_db
class TestOtherUsers:
    def test_unlisted_user_writes(self, client, monkeypatch, v1, issue):
        monkeypatch.setenv(SETTING, str(uuid.uuid4()))
        response = client.post(v1(f"work-items/{issue.id}/comments/"), {"comment_html": "<p>x</p>"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_unset_setting_changes_nothing(self, client, monkeypatch, v1, issue):
        monkeypatch.delenv(SETTING, raising=False)
        response = client.patch(v1(f"work-items/{issue.id}/"), {"name": "Changed"}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_bad_token_still_refused_as_before(self, api_client, read_only, v1, issue):
        api_client.credentials(HTTP_X_API_KEY="not-a-token")
        response = api_client.post(v1("work-items/"), {"name": "x"}, format="json")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        assert response.json()["detail"] == "Given API token is not valid"
