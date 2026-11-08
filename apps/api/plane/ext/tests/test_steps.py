# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
import uuid
from unittest import mock

import pytest
from django.urls import resolve
from rest_framework import status

from plane.db.models import Issue, IssueActivity, IssueAssignee, User, WorkspaceMember
from plane.db.models.api import APIToken
from plane.ext.models import WorkItemStep
from plane.ext.pql import Context, PQLError, compile_pql
from plane.ext.steps import (
    StepDetailEndpoint,
    StepListCreateEndpoint,
    StepReorderEndpoint,
    StepSetPathEndpoint,
    WorkItemByIdentifierAPIEndpoint,
    WorkItemDetailAPIEndpoint,
)
from plane.ext.tests.conftest import make_issue, make_project


def view_of(path):
    func = resolve(path).func
    return getattr(func, "__wrapped__", func).cls


@pytest.mark.unit
@pytest.mark.parametrize("items", ["work-items", "issues"])
def test_step_routes_resolve_to_ext_views(items):
    base = f"/api/v1/workspaces/acme/projects/{uuid.uuid4()}/{items}/{uuid.uuid4()}/"
    assert view_of(base + "steps/") is StepListCreateEndpoint
    assert view_of(base + "steps/set-path/") is StepSetPathEndpoint
    assert view_of(base + "steps/reorder/") is StepReorderEndpoint
    assert view_of(base + f"steps/{uuid.uuid4()}/") is StepDetailEndpoint
    assert view_of(base) is WorkItemDetailAPIEndpoint
    assert view_of(f"/api/v1/workspaces/acme/{items}/SQ-12/") is WorkItemByIdentifierAPIEndpoint


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Steps", "ST")


@pytest.fixture
def item(project, create_user):
    issue = make_issue(project, "Ship it")
    IssueAssignee.objects.create(issue=issue, assignee=create_user, project=project, workspace=project.workspace)
    return issue


@pytest.fixture
def webhook():
    with mock.patch("plane.ext.steps.webhook_activity.delay") as delay:
        yield delay


@pytest.fixture
def client(clients, webhook):
    return clients.api_key


def steps_url(issue, tail="", items="work-items"):
    return f"/api/v1/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/{items}/{issue.id}/steps/{tail}"


def add(client, issue, **body):
    return client.post(steps_url(issue), body, format="json")


def set_path(client, issue, steps):
    return client.post(steps_url(issue, "set-path/"), {"steps": steps}, format="json")


def titles(response):
    return [step["title"] for step in response.json()]


def step_rows(issue):
    return IssueActivity.objects.filter(issue=issue, field="step").order_by("created_at")


@pytest.mark.contract
@pytest.mark.django_db
class TestSteps:
    def test_add_appends_and_lists_in_order(self, client, item):
        assert add(client, item, title="build").status_code == status.HTTP_201_CREATED
        assert add(client, item, title="ship").status_code == status.HTTP_201_CREATED
        response = add(client, item, title="test", position=1)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["status"] == "pending" and response.json()["actor"] is None
        listed = client.get(steps_url(item))
        assert titles(listed) == ["build", "test", "ship"]
        assert [s["sort_order"] for s in listed.json()] == [1000.0, 2000.0, 3000.0]

    def test_issues_prefix_works_too(self, client, item):
        response = client.post(steps_url(item, items="issues"), {"title": "a"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert titles(client.get(steps_url(item, items="issues"))) == ["a"]

    @pytest.mark.parametrize("position", [-1, 2, "1", True, 1.5])
    def test_add_rejects_a_bad_position(self, client, item, position):
        add(client, item, title="a")
        response = add(client, item, title="b", position=position)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "position" in response.json()["error"]

    def test_add_validates_fields(self, client, item):
        assert add(client, item).status_code == status.HTTP_400_BAD_REQUEST
        assert add(client, item, title="a", status="maybe").status_code == status.HTTP_400_BAD_REQUEST
        assert not WorkItemStep.objects.exists()

    def test_actor_is_optional_and_must_be_a_workspace_member(self, client, item, create_user):
        stranger = User.objects.create(email="stranger@plane.so", username="stranger")
        assert add(client, item, title="a", actor=str(stranger.id)).status_code == status.HTTP_400_BAD_REQUEST
        response = add(client, item, title="a", actor=str(create_user.id))
        assert response.json()["actor"] == str(create_user.id)
        cleared = client.patch(steps_url(item, f"{response.json()['id']}/"), {"actor": None}, format="json")
        assert cleared.json()["actor"] is None

    def test_finish_with_a_note(self, client, item):
        step = add(client, item, title="build").json()
        response = client.patch(steps_url(item, f"{step['id']}/"), {"status": "done", "note": "green"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert (response.json()["status"], response.json()["note"]) == ("done", "green")
        assert client.get(steps_url(item, f"{step['id']}/")).json()["note"] == "green"

    def test_delete(self, client, item):
        step = add(client, item, title="build").json()
        assert client.delete(steps_url(item, f"{step['id']}/")).status_code == status.HTTP_204_NO_CONTENT
        assert client.get(steps_url(item)).json() == []
        assert client.get(steps_url(item, f"{step['id']}/")).status_code == status.HTTP_404_NOT_FOUND

    def test_a_step_of_another_item_is_not_found(self, client, item, project):
        other = make_issue(project, "Other")
        step = add(client, other, title="theirs").json()
        assert client.get(steps_url(item, f"{step['id']}/")).status_code == status.HTTP_404_NOT_FOUND
        patched = client.patch(steps_url(item, f"{step['id']}/"), {"status": "done"}, format="json")
        assert patched.status_code == status.HTTP_404_NOT_FOUND
        assert WorkItemStep.objects.get(pk=step["id"]).status == "pending"

    def test_unknown_item_is_not_found(self, client, item):
        item.id = uuid.uuid4()
        assert client.get(steps_url(item)).status_code == status.HTTP_404_NOT_FOUND
        assert add(client, item, title="a").status_code == status.HTTP_404_NOT_FOUND

    def test_needs_project_membership(self, clients, item, workspace):
        user = User.objects.create(email="guest@plane.so", username="guest")
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
        token = APIToken.objects.create(user=user, label="guest", token="token-guest").token
        clients.anon.credentials(HTTP_X_API_KEY=token)
        assert clients.anon.get(steps_url(item)).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
@pytest.mark.django_db
class TestSetPathAndReorder:
    def test_set_path_creates_updates_deletes_and_orders(self, client, item):
        keep = add(client, item, title="keep").json()
        drop = add(client, item, title="drop").json()
        response = set_path(client, item, [{"title": "first"}, {"id": keep["id"], "status": "done"}, {"title": "last"}])
        assert response.status_code == status.HTTP_200_OK
        assert titles(response) == ["first", "keep", "last"]
        assert response.json()[1]["status"] == "done" and response.json()[1]["id"] == keep["id"]
        assert not WorkItemStep.all_objects.filter(pk=drop["id"]).exists()

    def test_set_path_empty_clears(self, client, item):
        add(client, item, title="a")
        assert set_path(client, item, []).json() == []

    @pytest.mark.parametrize(
        "steps, complaint",
        [
            ("nope", "steps must be a list"),
            (["x"], "steps must be a list"),
            ([{"id": "not-a-uuid", "title": "a"}], "is not a step id"),
            ([{"id": str(uuid.uuid4()), "title": "a"}], "not steps of this work item"),
        ],
    )
    def test_set_path_rejects(self, client, item, steps, complaint):
        add(client, item, title="kept")
        response = set_path(client, item, steps)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert complaint in response.json()["error"]
        assert titles(client.get(steps_url(item))) == ["kept"]

    def test_set_path_rejects_a_repeated_id(self, client, item):
        step = add(client, item, title="a").json()
        response = set_path(client, item, [{"id": step["id"]}, {"id": step["id"]}])
        assert "twice" in response.json()["error"]

    def test_set_path_writes_nothing_when_one_entry_is_invalid(self, client, item):
        add(client, item, title="kept")
        response = set_path(client, item, [{"title": "fine"}, {"title": ""}])
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "1" in response.json()["steps"]
        assert titles(client.get(steps_url(item))) == ["kept"]

    def test_reorder(self, client, item):
        a, b, c = (add(client, item, title=t).json()["id"] for t in "abc")
        response = client.post(steps_url(item, "reorder/"), {"step_ids": [c, a, b]}, format="json")
        assert titles(response) == ["c", "a", "b"]

    @pytest.mark.parametrize("pick", [lambda a, b: [a], lambda a, b: [a, b, a], lambda a, b: [a, str(uuid.uuid4())]])
    def test_reorder_must_name_every_step_once(self, client, item, pick):
        a, b = (add(client, item, title=t).json()["id"] for t in "ab")
        response = client.post(steps_url(item, "reorder/"), {"step_ids": pick(a, b)}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert titles(client.get(steps_url(item))) == ["a", "b"]


@pytest.mark.contract
@pytest.mark.django_db
class TestHistory:
    def test_each_write_is_one_activity_row(self, client, item, create_user):
        step = add(client, item, title="build").json()
        client.patch(steps_url(item, f"{step['id']}/"), {"status": "done"}, format="json")
        set_path(client, item, [{"id": step["id"]}, {"title": "a"}, {"title": "b"}])
        ids = [s["id"] for s in client.get(steps_url(item)).json()]
        client.post(steps_url(item, "reorder/"), {"step_ids": ids[::-1]}, format="json")
        client.delete(steps_url(item, f"{step['id']}/"))
        rows = list(step_rows(item))
        assert [r.verb for r in rows] == ["created", "updated", "updated", "updated", "deleted"]
        assert all(r.actor_id == create_user.id and r.project_id == item.project_id for r in rows)
        created, finished, path, reorder, deleted = rows
        assert created.old_value is None and json.loads(created.new_value)["title"] == "build"
        assert created.new_identifier == uuid.UUID(step["id"]) and created.old_identifier is None
        assert json.loads(finished.old_value)["status"] == "pending"
        assert json.loads(finished.new_value)["status"] == "done"
        assert "status" in finished.comment
        assert [s["title"] for s in json.loads(path.new_value)] == ["build", "a", "b"]
        assert path.new_identifier is None
        assert [s["title"] for s in json.loads(reorder.new_value)] == ["b", "a", "build"]
        assert deleted.new_value is None and deleted.old_identifier == uuid.UUID(step["id"])

    def test_noop_writes_record_nothing(self, client, item):
        step = add(client, item, title="a").json()
        client.patch(steps_url(item, f"{step['id']}/"), {"title": "a"}, format="json")
        client.post(steps_url(item, "reorder/"), {"step_ids": [step["id"]]}, format="json")
        set_path(client, item, [{"id": step["id"]}])
        assert step_rows(item).count() == 1

    def test_writes_bump_updated_at_and_leave_state_and_assignees(self, client, item, project, create_user):
        Issue.all_objects.filter(pk=item.pk).update(updated_at="2020-01-01T00:00:00Z")
        state = item.state_id
        add(client, item, title="a")
        item.refresh_from_db()
        assert item.updated_at.year > 2020
        assert item.state_id == state
        assert list(IssueAssignee.objects.filter(issue=item).values_list("assignee_id", flat=True)) == [create_user.id]

    def test_a_failed_write_records_nothing(self, client, item):
        add(client, item, title="a", status="maybe")
        assert not step_rows(item).exists()

    def test_webhook_fires_after_commit_as_an_issue_update(
        self, client, item, webhook, create_user, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            step = add(client, item, title="build").json()
        kwargs = webhook.call_args.kwargs
        assert (kwargs["event"], kwargs["verb"], kwargs["field"]) == ("issue", "updated", "step")
        assert kwargs["event_id"] == str(item.id) and kwargs["slug"] == item.workspace.slug
        assert kwargs["actor_id"] == str(create_user.id)
        assert kwargs["old_value"] is None and kwargs["new_value"]["id"] == step["id"]
        assert kwargs["new_identifier"] == step["id"]
        json.dumps(kwargs)  # celery's json serializer must take it

    def test_no_webhook_when_the_write_fails(self, client, item, webhook, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            add(client, item, title="")
        webhook.assert_not_called()


@pytest.mark.contract
@pytest.mark.django_db
class TestItemRead:
    def detail(self, item, items="work-items"):
        return f"/api/v1/workspaces/{item.workspace.slug}/projects/{item.project_id}/{items}/{item.id}/"

    def test_without_step_fields_the_read_is_upstream(self, client, item):
        body = client.get(self.detail(item)).json()
        assert body["id"] == str(item.id) and "steps" not in body and "current_step" not in body

    def test_steps_and_current_step(self, client, item):
        done = add(client, item, title="build").json()
        client.patch(steps_url(item, f"{done['id']}/"), {"status": "done"}, format="json")
        add(client, item, title="test")
        body = client.get(self.detail(item), {"fields": "steps,current_step"}).json()
        assert set(body) == {"id", "steps", "current_step"}
        assert [s["title"] for s in body["steps"]] == ["build", "test"]
        assert body["current_step"]["title"] == "test"

    def test_mixed_fields(self, client, item):
        body = client.get(self.detail(item, "issues"), {"fields": "name,current_step"}).json()
        assert body == {"name": "Ship it", "current_step": None}

    def test_by_identifier(self, client, item, workspace):
        add(client, item, title="build")
        url = f"/api/v1/workspaces/{workspace.slug}/work-items/{item.project.identifier}-{item.sequence_id}/"
        body = client.get(url, {"fields": "id,current_step"}).json()
        assert body["id"] == str(item.id) and body["current_step"]["title"] == "build"

    def test_patch_still_upstream(self, client, item):
        response = client.patch(self.detail(item), {"name": "Renamed"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        item.refresh_from_db()
        assert item.name == "Renamed"

    @pytest.mark.parametrize(
        "statuses, current",
        [
            (["done", "pending", "pending"], 1),
            (["done", "failed", "pending"], 1),  # a failure holds the path
            (["skipped", "done", "pending"], 2),
            (["done", "skipped"], None),
            ([], None),
        ],
    )
    def test_current_step_rule(self, client, item, statuses, current):
        set_path(client, item, [{"title": str(i), "status": s} for i, s in enumerate(statuses)])
        body = client.get(self.detail(item), {"fields": "current_step"}).json()
        assert (body["current_step"] or {}).get("title") == (None if current is None else str(current))


@pytest.mark.unit
def test_step_actor_rejects_a_non_uuid():
    with pytest.raises(PQLError, match="stepActor takes a UUID"):
        compile_pql('stepActor = "me"', Context(user_id=uuid.uuid4(), workspace_slug="acme"))


@pytest.mark.django_db
class TestStepActorPQL:
    @pytest.fixture
    def setup(self, workspace, create_user):
        project = make_project(workspace, create_user, "Queue", "QU")
        other = User.objects.create(email="b@plane.so", username="b")
        WorkspaceMember.objects.create(workspace=workspace, member=other, role=15)

        def item(name, *steps):
            issue = make_issue(project, name)
            for order, (step_status, actor) in enumerate(steps):
                WorkItemStep.objects.create(
                    issue=issue,
                    project=project,
                    title=f"{name}{order}",
                    status=step_status,
                    actor=actor,
                    sort_order=order,
                )
            return issue

        item("mine-now", ("done", other), ("pending", create_user), ("pending", other))
        item("mine-failed", ("failed", create_user), ("pending", other))
        item("theirs-now", ("done", create_user), ("pending", other))
        item("theirs-after-skip", ("skipped", create_user), ("pending", other))
        item("unowned-now", ("pending", None), ("pending", create_user))
        item("finished", ("done", create_user))
        item("no-steps")
        return project, create_user, other

    def run(self, setup, pql):
        project, user, _ = setup
        q = compile_pql(pql, Context(user_id=user.id, workspace_slug=project.workspace.slug))
        return sorted(Issue.objects.filter(project=project).filter(q).values_list("name", flat=True))

    def test_current_user(self, setup):
        assert self.run(setup, "stepActor = currentUser()") == ["mine-failed", "mine-now"]

    def test_by_id_and_in(self, setup):
        _, user, other = setup
        assert self.run(setup, f'stepActor = "{other.id}"') == ["theirs-after-skip", "theirs-now"]
        both = self.run(setup, f'stepActor IN ("{user.id}", "{other.id}")')
        assert both == ["mine-failed", "mine-now", "theirs-after-skip", "theirs-now"]

    def test_not_equal_includes_items_without_a_current_step(self, setup):
        assert self.run(setup, "stepActor != currentUser()") == [
            "finished",
            "no-steps",
            "theirs-after-skip",
            "theirs-now",
            "unowned-now",
        ]

    def test_is_null_means_the_current_step_has_no_actor(self, setup):
        assert self.run(setup, "stepActor IS NULL") == ["unowned-now"]

    def test_is_not_null_means_the_current_step_has_an_actor(self, setup):
        assert self.run(setup, "stepActor IS NOT NULL") == [
            "mine-failed",
            "mine-now",
            "theirs-after-skip",
            "theirs-now",
        ]

    def test_combines_with_other_fields(self, setup):
        assert self.run(setup, 'stepActor = currentUser() AND title ~ "failed"') == ["mine-failed"]

    def test_over_the_list_route(self, clients, setup, webhook):
        project, _, _ = setup
        url = f"/api/v1/workspaces/{project.workspace.slug}/projects/{project.id}/work-items/"
        response = clients.api_key.get(url, {"pql": "stepActor = currentUser()"})
        assert response.status_code == status.HTTP_200_OK
        assert sorted(item["name"] for item in response.json()["results"]) == ["mine-failed", "mine-now"]
