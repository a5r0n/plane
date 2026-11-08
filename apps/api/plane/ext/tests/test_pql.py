# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid
from datetime import timedelta

import pytest
from django.urls import resolve
from django.utils import timezone

from plane.db.models import Issue, IssueAssignee, IssueLabel, Label, State, User, WorkspaceMember
from plane.ext.pql import Context, PQLError, compile_pql
from plane.ext.tests.conftest import make_issue, make_project
from plane.ext.work_items import WorkItemListCreateAPIEndpoint

CTX = Context(user_id=uuid.uuid4(), workspace_slug="acme")
STATE = str(uuid.uuid4())


@pytest.mark.unit
@pytest.mark.parametrize("tail", ["work-items/", "issues/"])
def test_list_routes_resolve_to_ext_view(tail):
    match = resolve(f"/api/v1/workspaces/acme/projects/{uuid.uuid4()}/{tail}")
    assert match.func.__wrapped__.cls is WorkItemListCreateAPIEndpoint  # under the epic hiding wrapper


@pytest.mark.unit
@pytest.mark.parametrize(
    "pql, complaint",
    [
        ("", "empty"),
        ('priority = "urgent" AND', "ends too early"),
        ('stat = "done"', "unsupported field 'stat'"),
        ('priority = "huge"', "priority is one of"),
        ('stateGroup = "doing"', "stateGroup is one of"),
        ('state = "Todo"', "state takes a UUID"),
        ("assignee = me", "expected a quoted value"),
        ("cycle IN activeCycle()", "unsupported field 'cycle'"),
        ("isOverdue()", "unsupported function isOverdue()"),
        ("priority IN openStates()", "fits stateGroup only"),
        ("label = currentUser()", "fits assignee, createdBy or stepActor"),
        ('dueDate BETWEEN ("2026-01-01", "2026-02-01")', "expected an operator"),
        ('dueDate < "tomorrow"', "dates are YYYY-MM-DD"),
        ('priority > "low"', "date fields only"),
        ('priority ~ "ur"', "'~' works on title only"),
        ('(priority = "high"', "expected ')'"),
        ('priority = "high")', "unexpected ')'"),
        ('title ~ "x" # y', "unexpected character '#'"),
        ('childOf("not an id")', "childOf() takes a work item id"),
        ("dueDate < daysAgo(99999999999)", "out of the date range"),
        ("dueDate < daysAgo(3000000)", "out of the date range"),
        ("dueDate > daysFromNow(3000000)", "out of the date range"),
        ("(" * 2000 + 'priority = "high"' + ")" * 2000, "nests ( or NOT more than"),
        ("NOT " * 2000 + 'priority = "high"', "nests ( or NOT more than"),
    ],
)
def test_rejects_with_a_reason(pql, complaint):
    with pytest.raises(PQLError) as exc:
        compile_pql(pql, CTX)
    assert complaint in str(exc.value)


@pytest.mark.unit
def test_keywords_are_case_insensitive_and_quotes_either_kind():
    a = compile_pql(f"state = '{STATE}' and not priority in (\"low\", 'none')", CTX)
    b = compile_pql(f'state = "{STATE}" AND NOT priority IN ("low", "none")', CTX)
    assert str(a) == str(b)


@pytest.fixture
def setup(db, workspace, create_user):
    """Two projects; items in the first cover each field, the second holds a decoy."""
    project = make_project(workspace, create_user, "Queue", "QU")
    other = make_project(workspace, create_user, "Other", "OQ")
    ready = State.objects.create(name="Ready", project=project, workspace=workspace, group="unstarted")
    done = State.objects.create(name="Done", project=project, workspace=workspace, group="completed")
    label = Label.objects.create(name="gap", project=project, workspace=workspace)
    teammate = User.objects.create(email="mate@plane.so", username="mate")
    WorkspaceMember.objects.create(workspace=workspace, member=teammate, role=15)
    common = {"project": project, "workspace": workspace}

    mine = make_issue(project, "Mine ready", state=ready, priority="high")
    IssueAssignee.objects.create(issue=mine, assignee=create_user, **common)
    IssueLabel.objects.create(issue=mine, label=label, **common)
    theirs = make_issue(project, "Theirs ready", state=ready, priority="low", parent=mine)
    IssueAssignee.objects.create(issue=theirs, assignee=teammate, **common)
    finished = make_issue(project, "Mine done", state=done, priority="urgent")
    IssueAssignee.objects.create(issue=finished, assignee=create_user, **common)
    IssueAssignee.objects.create(issue=finished, assignee=teammate, **common)
    loose = make_issue(project, "Nobody's", priority="none")
    Issue.objects.filter(pk=loose.pk).update(target_date=timezone.localdate() - timedelta(days=3))
    removed = make_issue(project, "Unassigned since", state=ready)
    IssueAssignee.objects.create(issue=removed, assignee=create_user, **common).delete()  # soft delete
    make_issue(other, "Decoy in other project", priority="high")

    return {
        "url": f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/",
        "project": project,
        "ready": ready,
        "label": label,
        "teammate": teammate,
        "names": {i.name: i for i in (mine, theirs, finished, loose, removed)},
    }


def names(response):
    assert response.status_code == 200, response.data
    return sorted(row["name"] for row in response.data["results"])


@pytest.mark.contract
@pytest.mark.django_db
class TestListWithPQL:
    @pytest.mark.parametrize("tail", ["work-items/", "issues/"])
    def test_my_queue(self, api_key_client, setup, tail):
        pql = 'assignee = currentUser() AND stateGroup = "unstarted"'
        response = api_key_client.get(setup["url"] + tail, {"pql": pql})
        assert names(response) == ["Mine ready"]
        assert response.data["total_count"] == 1

    @pytest.mark.parametrize(
        "pql, expected",
        [
            ('priority IN ("high", "urgent")', ["Mine done", "Mine ready"]),
            ('priority = "high" OR priority = "none"', ["Mine ready", "Nobody's", "Unassigned since"]),
            ("stateGroup IN openStates() AND NOT hasNoAssignee()", ["Mine ready", "Theirs ready"]),
            ("assignee != currentUser()", ["Nobody's", "Theirs ready", "Unassigned since"]),
            ("hasNoAssignee()", ["Nobody's", "Unassigned since"]),
            ('title ~ "MINE"', ["Mine done", "Mine ready"]),
            ("isTopLevel() AND label IS NOT NULL", ["Mine ready"]),
            ('childOf("QU-1")', ["Theirs ready"]),
            ('childOf("QU-999")', []),
            ("dueDate < today()", ["Nobody's"]),
            ("dueDate >= daysAgo(3) AND dueDate <= daysFromNow(1)", ["Nobody's"]),
            ("createdAt >= today()", ["Mine done", "Mine ready", "Nobody's", "Theirs ready", "Unassigned since"]),
            ('NOT (priority = "low" OR priority = "none") AND stateGroup NOT IN closedStates()', ["Mine ready"]),
        ],
    )
    def test_filters(self, api_key_client, setup, pql, expected):
        assert names(api_key_client.get(setup["url"] + "work-items/", {"pql": pql})) == expected

    def test_uuid_fields(self, api_key_client, setup):
        cases = {
            f'state = "{setup["ready"].id}"': ["Mine ready", "Theirs ready", "Unassigned since"],
            f'label = "{setup["label"].id}"': ["Mine ready"],
            f'assignee IN ("{setup["teammate"].id}")': ["Mine done", "Theirs ready"],
            f'parent = "{setup["names"]["Mine ready"].id}"': ["Theirs ready"],
        }
        for pql, expected in cases.items():
            assert names(api_key_client.get(setup["url"] + "work-items/", {"pql": pql})) == expected, pql

    def test_stays_in_the_project(self, api_key_client, setup):
        assert names(api_key_client.get(setup["url"] + "work-items/", {"pql": 'priority = "high"'})) == ["Mine ready"]

    def test_epics_stay_hidden(self, api_key_client, setup):
        make_issue(setup["project"], "Epic high", epic=True, priority="high")
        assert names(api_key_client.get(setup["url"] + "work-items/", {"pql": 'priority = "high"'})) == ["Mine ready"]

    def test_paging_counts_the_filtered_set(self, api_key_client, setup):
        response = api_key_client.get(
            setup["url"] + "work-items/", {"pql": "stateGroup IN openStates()", "per_page": 1}
        )
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["total_count"] == 4
        assert response.data["next_page_results"] is True

    def test_invalid_pql_is_a_400_the_mcp_can_read(self, api_key_client, setup):
        response = api_key_client.get(setup["url"] + "work-items/", {"pql": "isOverdue()"})
        assert response.status_code == 400
        assert "isOverdue()" in response.data["pql"]

    def test_without_pql_lists_everything(self, api_key_client, setup):
        assert len(names(api_key_client.get(setup["url"] + "work-items/"))) == 5

    def test_structured_filters_still_refused(self, api_key_client, setup):
        response = api_key_client.get(setup["url"] + "work-items/", {"filters": '{"priority":"high"}'})
        assert response.status_code == 400
        assert response.data["unsupported_parameters"] == ["filters"]

    def test_create_still_works(self, api_key_client, setup):
        response = api_key_client.post(setup["url"] + "work-items/", {"name": "Created"}, format="json")
        assert response.status_code == 201
