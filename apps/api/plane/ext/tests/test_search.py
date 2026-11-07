# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.urls import resolve
from django.utils import timezone
from rest_framework import status

from plane.db.models import Issue, IssueComment, Project, ProjectMember, State
from plane.ext.search import WorkItemSearchEndpoint


def make_project(workspace, user, name, identifier, member=True):
    project = Project.objects.create(name=name, identifier=identifier, workspace=workspace, created_by=user)
    if member:
        ProjectMember.objects.create(project=project, member=user, role=20, is_active=True)
    State.objects.create(name="Todo", project=project, workspace=workspace, group="backlog", default=True)
    return project


def make_issue(project, user, name, description_html="<p></p>"):
    return Issue.objects.create(
        name=name,
        description_html=description_html,
        workspace=project.workspace,
        project=project,
        created_by=user,
    )


def comment(issue, user, html):
    return IssueComment.objects.create(
        issue=issue,
        comment_html=html,
        workspace=issue.workspace,
        project=issue.project,
        actor=user,
        created_by=user,
    )


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Search Project", "SP")


def search(client, workspace, query, path="work-items", **params):
    return client.get(f"/api/v1/workspaces/{workspace.slug}/{path}/search/", {"search": query, **params})


def names(response):
    return [r["name"] for r in response.data["issues"]]


@pytest.mark.unit
@pytest.mark.parametrize("path", ["work-items", "issues"])
def test_search_routes_resolve_to_ext_view(path):
    match = resolve(f"/api/v1/workspaces/acme/{path}/search/")
    assert match.func.view_class is WorkItemSearchEndpoint


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkItemSearch:
    def test_matches_description(self, api_key_client, workspace, project, create_user):
        make_issue(project, create_user, "Plain title", "<p>the quokka hides here</p>")
        response = search(api_key_client, workspace, "QUOKKA")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["issues"][0]["name"] == "Plain title"
        assert response.data["issues"][0]["matched"] == "description"

    def test_matches_comment(self, api_key_client, workspace, project, create_user):
        issue = make_issue(project, create_user, "Plain title")
        comment(issue, create_user, "<p>a quokka in the comments</p>")
        response = search(api_key_client, workspace, "quokka")
        assert [(r["name"], r["matched"]) for r in response.data["issues"]] == [("Plain title", "comment")]

    def test_deleted_comment_does_not_match(self, api_key_client, workspace, project, create_user):
        issue = make_issue(project, create_user, "Plain title")
        c = comment(issue, create_user, "<p>quokka</p>")
        IssueComment.all_objects.filter(pk=c.pk).update(deleted_at=timezone.now())
        assert names(search(api_key_client, workspace, "quokka")) == []

    def test_title_ranks_before_description_before_comment(self, api_key_client, workspace, project, create_user):
        # created oldest first, so recency alone would give the reverse order
        make_issue(project, create_user, "quokka in title")
        make_issue(project, create_user, "Description hit", "<p>quokka</p>")
        comment(make_issue(project, create_user, "Comment hit"), create_user, "<p>quokka</p>")
        response = search(api_key_client, workspace, "quokka")
        assert [(r["name"], r["matched"]) for r in response.data["issues"]] == [
            ("quokka in title", "title"),
            ("Description hit", "description"),
            ("Comment hit", "comment"),
        ]

    def test_item_matching_several_ways_is_listed_once(self, api_key_client, workspace, project, create_user):
        issue = make_issue(project, create_user, "quokka title", "<p>quokka</p>")
        comment(issue, create_user, "<p>quokka</p>")
        comment(issue, create_user, "<p>another quokka</p>")
        response = search(api_key_client, workspace, "quokka")
        assert [(r["name"], r["matched"]) for r in response.data["issues"]] == [("quokka title", "title")]

    def test_upstream_matches_still_work(self, api_key_client, workspace, project, create_user):
        issue = make_issue(project, create_user, "Plain title")
        by_number = search(api_key_client, workspace, str(issue.sequence_id))
        assert "Plain title" in names(by_number)
        assert "Plain title" in names(search(api_key_client, workspace, "sp"))
        assert set(by_number.data["issues"][0]) == {
            "name",
            "id",
            "sequence_id",
            "project__identifier",
            "project_id",
            "workspace__slug",
            "matched",
        }

    def test_non_member_project_is_hidden(self, api_key_client, workspace, project, create_user):
        other = make_project(workspace, create_user, "Other", "OT", member=False)
        make_issue(other, create_user, "Hidden", "<p>quokka</p>")
        assert names(search(api_key_client, workspace, "quokka")) == []

    def test_project_filter_and_limit(self, api_key_client, workspace, project, create_user):
        other = make_project(workspace, create_user, "Other", "OT")
        make_issue(other, create_user, "Other hit", "<p>quokka</p>")
        for i in range(3):
            make_issue(project, create_user, f"Hit {i}", "<p>quokka</p>")
        scoped = search(api_key_client, workspace, "quokka", project_id=str(project.id))
        assert sorted(names(scoped)) == ["Hit 0", "Hit 1", "Hit 2"]
        assert len(names(search(api_key_client, workspace, "quokka", limit=2))) == 2

    def test_legacy_issues_path(self, api_key_client, workspace, project, create_user):
        make_issue(project, create_user, "Plain title", "<p>quokka</p>")
        assert names(search(api_key_client, workspace, "quokka", path="issues")) == ["Plain title"]

    def test_empty_query(self, api_key_client, workspace, project):
        assert search(api_key_client, workspace, "").data == {"issues": []}
