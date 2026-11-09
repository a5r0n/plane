# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.urls import resolve
from django.utils import timezone

from plane.db.models import Issue, IssueAssignee, IssueLabel, Label, State, User, WorkspaceMember
from plane.ext.models import CustomProperty, CustomValue
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
        ("dueDate < daysAgo(1.5)", "whole number of days"),
        ('prop.repo = "plane"', "a project's work item list"),
        ('label.x = "a"', "unsupported field 'label.x'"),
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


@pytest.fixture
def props(db, workspace, create_user):
    """Items A, B and an unset C, over one property of each type."""
    project = make_project(workspace, create_user, "Props", "PR")
    options = [{"id": i, "label": i.title(), "disabled": i == "old"} for i in ("plane", "mcp", "old")]
    T = CustomProperty.Type

    def define(key, type, **fields):
        return CustomProperty.objects.create(
            project=project, workspace=workspace, name=key.title(), key=key, type=type, **fields
        )

    defs = {
        "repo": define("repo", T.CHOICE, options=options),
        "tags": define("tags", T.CHOICE, options=options, multiple=True),
        "count": define("count", T.NUMBER),
        "done": define("done", T.BOOLEAN),
        "when": define("when", T.DATE),
        "at": define("at", T.DATETIME),
        "owner": define("owner", T.MEMBER),
        "note": define("note", T.TEXT),
        "site": define("site", T.URL),
        "gone": define("gone", T.TEXT),
    }
    a, b, c = (make_issue(project, name) for name in ("A", "B", "C"))

    def hold(issue, key, **column):
        CustomValue.objects.create(project=project, workspace=workspace, issue=issue, property=defs[key], **column)

    hold(a, "repo", value_text="plane")
    hold(b, "repo", value_text="old")
    hold(a, "tags", value_text="plane", position=0)
    hold(a, "tags", value_text="mcp", position=1)
    hold(b, "tags", value_text="mcp")
    hold(a, "count", value_number=Decimal("2.5"))
    hold(b, "count", value_number=3)
    hold(a, "done", value_bool=True)
    hold(b, "done", value_bool=False)
    hold(a, "when", value_date=date(2025, 6, 1))
    hold(b, "when", value_date=date(2026, 6, 1))
    hold(a, "at", value_datetime=datetime(2026, 1, 1, 12, tzinfo=dt_timezone.utc))
    hold(a, "owner", value_member=create_user)
    hold(a, "note", value_text="Fix login")
    hold(b, "note", value_text="docs")
    hold(b, "site", value_text="https://example.com/fix")
    hold(a, "gone", value_text="x")
    defs["gone"].delete()  # soft delete; its key stays reserved and unknown to PQL
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"


@pytest.mark.contract
@pytest.mark.django_db
class TestProperties:
    @pytest.mark.parametrize(
        "pql, expected",
        [
            ('prop.repo = "plane"', ["A"]),
            ('prop.repo != "plane"', ["B", "C"]),
            ('prop.repo = "old"', ["B"]),  # a disabled option still filters
            ('prop.repo IN ("plane", "old")', ["A", "B"]),
            ('prop.repo NOT IN ("plane")', ["B", "C"]),
            ("prop.repo IS NULL", ["C"]),
            ("prop.repo IS NOT NULL", ["A", "B"]),
            ('prop.tags = "mcp"', ["A", "B"]),
            ('prop.tags != "plane"', ["B", "C"]),
            ("prop.count > 2", ["A", "B"]),
            ("prop.count = 2.5", ["A"]),
            ("prop.count <= 2.5", ["A"]),
            ("prop.count != 3", ["A", "C"]),
            ("prop.done = TRUE", ["A"]),
            ("prop.done = FALSE", ["B"]),
            ('prop.when < "2026-01-01"', ["A"]),
            ("prop.when > daysAgo(3650)", ["A", "B"]),
            ('prop.at >= "2026-01-01T12:00:00Z"', ["A"]),
            ('prop.at < "2026-01-01T13:00:00+02:00"', []),
            ("prop.owner = currentUser()", ["A"]),
            ('prop.note ~ "fix"', ["A"]),
            ('prop.note = "docs"', ["B"]),
            ('prop.site ~ "/fix"', ["B"]),
            ('prop.repo = "old" AND prop.count > 2', ["B"]),
            ("NOT prop.done = TRUE", ["B", "C"]),
        ],
    )
    def test_filters(self, api_key_client, props, pql, expected):
        assert names(api_key_client.get(props, {"pql": pql})) == expected

    @pytest.mark.parametrize(
        "pql, complaint",
        [
            ('prop.nope = "x"', "unknown property 'prop.nope'"),
            ('prop.gone = "x"', "unknown property 'prop.gone'"),
            ('prop.repo > "a"', "'>' works on number, date and datetime properties"),
            ('prop.count ~ "1"', "'~' works on text and url properties"),
            ('prop.repo = "nope"', "prop.repo is one of plane, mcp, old"),
            ('prop.count = "3"', "prop.count takes a number"),
            ('prop.done = "yes"', "prop.done takes TRUE or FALSE"),
            ('prop.owner = "abc"', "prop.owner takes a user id"),
            ('prop.when = "June"', "dates are YYYY-MM-DD"),
            ('prop.at = "2026-01-01T12:00:00"', "prop.at takes an ISO 8601 timestamp with a time zone"),
            ("prop.note = currentUser()", "currentUser() fits"),
        ],
    )
    def test_rejects_with_a_reason(self, api_key_client, props, pql, complaint):
        response = api_key_client.get(props, {"pql": pql})
        assert response.status_code == 400
        assert complaint in response.data["pql"]
