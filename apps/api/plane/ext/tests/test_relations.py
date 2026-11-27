# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid
from unittest import mock

import pytest
from django.urls import resolve
from rest_framework import status

from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import Issue, IssueActivity, IssueRelation, Project, ProjectMember, User, WorkspaceMember
from plane.db.models.api import APIToken
from plane.ext.relations import WorkItemRelationRemoveEndpoint


@pytest.fixture
def activity():
    """Capture the activity task's calls; run() replays them synchronously."""
    with mock.patch("plane.ext.relations.issue_activity.delay") as delay:

        def run():
            with mock.patch("plane.bgtasks.issue_activities_task.notifications.delay"):
                for call in delay.call_args_list:
                    issue_activity(**call.kwargs)

        delay.run = run
        yield delay


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Rel", identifier="REL", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


def make_issue(project, user, name):
    return Issue.objects.create(name=name, workspace=project.workspace, project=project, created_by=user)


def relate(issue, related, relation_type):
    return IssueRelation.objects.create(
        issue=issue,
        related_issue=related,
        relation_type=relation_type,
        project=issue.project,
        workspace=issue.workspace,
    )


def relations_url(issue):
    return f"/api/v1/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/work-items/{issue.id}/relations/"


def remove(client, issue, related_id):
    return client.post(relations_url(issue) + "remove/", {"related_issue": str(related_id)}, format="json")


def other_member(project, role):
    user = User.objects.create(email="other@plane.so", username="other")
    WorkspaceMember.objects.create(workspace=project.workspace, member=user, role=role)
    ProjectMember.objects.create(project=project, member=user, role=role, is_active=True)
    return APIToken.objects.create(user=user, label="other", token="token-other").token


@pytest.mark.unit
def test_remove_route_resolves_to_ext_view():
    project_id, issue_id = uuid.uuid4(), uuid.uuid4()
    match = resolve(f"/api/v1/workspaces/acme/projects/{project_id}/work-items/{issue_id}/relations/remove/")
    assert match.func.cls is WorkItemRelationRemoveEndpoint


@pytest.mark.contract
@pytest.mark.django_db
class TestRemoveRelation:
    @pytest.fixture
    def pair(self, project, create_user):
        return make_issue(project, create_user, "A"), make_issue(project, create_user, "B")

    @pytest.mark.parametrize("from_related_side", [False, True])
    def test_removes_both_sides(self, api_key_client, pair, activity, from_related_side):
        a, b = pair
        relate(a, b, "blocked_by")
        caller, other = (b, a) if from_related_side else (a, b)

        response = remove(api_key_client, caller, other.id)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not IssueRelation.objects.filter(issue__in=pair).exists()
        for issue in pair:
            listed = api_key_client.get(relations_url(issue)).data
            assert all(entries == [] for entries in listed.values())

    @pytest.mark.parametrize(
        ("from_related_side", "caller_field", "other_field"),
        [(False, "blocked_by", "blocking"), (True, "blocking", "blocked_by")],
    )
    def test_activity_names_the_type_on_both_items(
        self, api_key_client, pair, activity, from_related_side, caller_field, other_field
    ):
        a, b = pair
        relate(a, b, "blocked_by")
        caller, other = (b, a) if from_related_side else (a, b)

        remove(api_key_client, caller, other.id)
        activity.run()

        caller_activity = IssueActivity.objects.get(issue=caller, verb="deleted")
        other_activity = IssueActivity.objects.get(issue=other, verb="deleted")
        assert caller_activity.field == caller_field
        assert other_activity.field == other_field
        assert caller_activity.old_value == f"REL-{other.sequence_id}"
        assert other_activity.old_value == f"REL-{caller.sequence_id}"

    def test_symmetric_type_is_kept(self, api_key_client, pair, activity):
        a, b = pair
        relate(a, b, "relates_to")

        assert remove(api_key_client, b, a.id).status_code == status.HTTP_204_NO_CONTENT
        activity.run()

        assert set(IssueActivity.objects.filter(verb="deleted").values_list("field", flat=True)) == {"relates_to"}

    def test_removes_only_that_pair(self, api_key_client, pair, project, create_user, activity):
        a, b = pair
        c = make_issue(project, create_user, "C")
        relate(a, b, "relates_to")
        kept = relate(a, c, "duplicate")

        remove(api_key_client, a, b.id)

        assert list(IssueRelation.objects.all()) == [kept]

    def test_missing_relation_is_not_found(self, api_key_client, pair, activity):
        a, b = pair
        assert remove(api_key_client, a, b.id).status_code == status.HTTP_404_NOT_FOUND
        activity.assert_not_called()

    def test_item_of_another_project_is_not_found(self, api_key_client, pair, workspace, create_user, activity):
        a, b = pair
        relate(a, b, "relates_to")
        elsewhere = Project.objects.create(name="Else", identifier="EL", workspace=workspace)
        ProjectMember.objects.create(project=elsewhere, member=create_user, role=20, is_active=True)
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{elsewhere.id}/work-items/{a.id}/relations/remove/"

        response = api_key_client.post(url, {"related_issue": str(b.id)}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert IssueRelation.objects.exists()

    @pytest.mark.parametrize("body", [{}, {"related_issue": "not-an-id"}])
    def test_bad_related_issue_is_rejected(self, api_key_client, pair, body, activity):
        a, _ = pair
        response = api_key_client.post(relations_url(a) + "remove/", body, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_guest_cannot_remove(self, api_client, pair, project, activity):
        a, b = pair
        relate(a, b, "relates_to")
        api_client.credentials(HTTP_X_API_KEY=other_member(project, role=5))

        assert remove(api_client, a, b.id).status_code == status.HTTP_403_FORBIDDEN
        assert IssueRelation.objects.exists()

    def test_requires_an_api_key(self, api_client, pair, activity):
        a, b = pair
        relate(a, b, "relates_to")

        assert remove(api_client, a, b.id).status_code == status.HTTP_401_UNAUTHORIZED
        assert IssueRelation.objects.exists()


UPSTREAM_KEYS = {
    "blocking",
    "blocked_by",
    "duplicate",
    "relates_to",
    "start_after",
    "start_before",
    "finish_after",
    "finish_before",
}


def ref(issue):
    return {"project_id": str(issue.project_id), "issue_id": str(issue.id)}


@pytest.mark.contract
@pytest.mark.django_db
class TestImplementsRelation:
    @pytest.fixture
    def pair(self, project, create_user):
        return make_issue(project, create_user, "Idea"), make_issue(project, create_user, "Build")

    @pytest.fixture(autouse=True)
    def create_activity(self):
        with mock.patch("plane.api.views.issue.issue_activity.delay") as delay:
            yield delay

    def create(self, client, issue, relation_type, related):
        return client.post(
            relations_url(issue), {"relation_type": relation_type, "issues": [str(related.id)]}, format="json"
        )

    @pytest.mark.parametrize("from_build_side", [False, True])
    def test_create_from_either_side_stores_one_row(self, api_key_client, pair, from_build_side):
        idea, build = pair
        if from_build_side:
            response = self.create(api_key_client, build, "implements", idea)
        else:
            response = self.create(api_key_client, idea, "implemented_by", build)

        assert response.status_code == status.HTTP_201_CREATED
        row = IssueRelation.objects.get()
        assert (row.issue_id, row.related_issue_id, row.relation_type) == (idea.id, build.id, "implemented_by")

        idea_view = api_key_client.get(relations_url(idea)).data
        build_view = api_key_client.get(relations_url(build)).data
        assert idea_view["implemented_by"] == [ref(build)]
        assert idea_view["implements"] == []
        assert build_view["implements"] == [ref(idea)]
        assert build_view["implemented_by"] == []

    def test_create_records_the_type_on_both_items(self, api_key_client, pair, create_activity):
        idea, build = pair
        self.create(api_key_client, build, "implements", idea)

        with mock.patch("plane.bgtasks.issue_activities_task.notifications.delay"):
            issue_activity(**create_activity.call_args.kwargs)

        assert IssueActivity.objects.get(issue=build, verb="updated").field == "implements"
        assert IssueActivity.objects.get(issue=idea, verb="updated").field == "implemented_by"

    @pytest.mark.parametrize(
        ("from_build_side", "caller_field", "other_field"),
        [(False, "implemented_by", "implements"), (True, "implements", "implemented_by")],
    )
    def test_remove_from_either_side_clears_both(
        self, api_key_client, pair, activity, from_build_side, caller_field, other_field
    ):
        idea, build = pair
        relate(idea, build, "implemented_by")
        caller, other = (build, idea) if from_build_side else (idea, build)

        assert remove(api_key_client, caller, other.id).status_code == status.HTTP_204_NO_CONTENT
        activity.run()

        assert not IssueRelation.objects.exists()
        for issue in pair:
            listed = api_key_client.get(relations_url(issue)).data
            assert listed["implemented_by"] == [] and listed["implements"] == []
        assert IssueActivity.objects.get(issue=caller, verb="deleted").field == caller_field
        assert IssueActivity.objects.get(issue=other, verb="deleted").field == other_field

    def test_unknown_type_is_rejected(self, api_key_client, pair):
        idea, build = pair
        response = self.create(api_key_client, idea, "built_by", build)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not IssueRelation.objects.exists()

    def test_existing_types_keep_their_shape(self, api_key_client, pair, project, create_user):
        idea, build = pair
        blocker = make_issue(project, create_user, "Blocker")
        relate(idea, blocker, "blocked_by")
        relate(idea, build, "implemented_by")

        listed = api_key_client.get(relations_url(idea)).data

        assert set(listed) == UPSTREAM_KEYS | {"implemented_by", "implements"}
        assert listed["blocked_by"] == [ref(blocker)]
        assert all(listed[key] == [] for key in UPSTREAM_KEYS - {"blocked_by"})
        assert api_key_client.get(relations_url(blocker)).data["blocking"] == [ref(idea)]


@pytest.mark.contract
@pytest.mark.django_db
class TestImplementsRelationSession:
    @pytest.fixture
    def pair(self, project, create_user):
        return make_issue(project, create_user, "Idea"), make_issue(project, create_user, "Build")

    def url(self, issue, tail):
        return f"/api/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/{tail}/"

    def test_create_from_build_side_and_list_both(self, session_client, pair):
        idea, build = pair
        with mock.patch("plane.app.views.issue.relation.issue_activity.delay"):
            response = session_client.post(
                self.url(build, "issue-relation"),
                {"relation_type": "implements", "issues": [str(idea.id)]},
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        row = IssueRelation.objects.get()
        assert (row.issue_id, row.related_issue_id, row.relation_type) == (idea.id, build.id, "implemented_by")

        idea_view = session_client.get(self.url(idea, "issue-relation")).data
        build_view = session_client.get(self.url(build, "issue-relation")).data
        assert [i["id"] for i in idea_view["implemented_by"]] == [build.id]
        assert [i["relation_type"] for i in idea_view["implemented_by"]] == ["implemented_by"]
        assert [i["id"] for i in build_view["implements"]] == [idea.id]
        assert idea_view["implements"] == [] and build_view["implemented_by"] == []
