# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import pytest

from plane.db.models import Issue
from plane.ext.tests.conftest import make_issue

pytestmark = pytest.mark.django_db

ENVELOPE = {
    "results",
    "total_count",
    "next_cursor",
    "prev_cursor",
    "next_page_results",
    "prev_page_results",
    "count",
    "total_pages",
    "total_results",
}


@pytest.fixture
def nested_epics(project, other_project):
    outer = make_issue(project, "Outer", epic=True)
    inner = make_issue(project, "Inner", epic=True, parent=outer)
    good = make_issue(project, "Good")
    ids = {
        "self": inner.id,
        "ancestor": outer.id,
        "other_project": make_issue(other_project, "Elsewhere").id,
        "unknown": uuid4(),
        "not_a_uuid": "nope",
    }
    return SimpleNamespace(outer=outer, inner=inner, good=good, ids=ids)


@pytest.fixture
def looped_epics(project):
    a = make_issue(project, "Loop a", epic=True)
    b = make_issue(project, "Loop b", epic=True, parent=a)
    Issue.objects.filter(pk=a.pk).update(parent=b)
    return SimpleNamespace(a=a, b=b)


@pytest.fixture
def normal_with_external_id(project):
    return make_issue(project, "External", external_id="x", external_source="y")


@pytest.fixture
def mock_activity():
    with mock.patch("plane.ext.epics.views.issue_activity.delay") as task:
        yield task


def test_create_and_list(api_key_client, v1, normal):
    created = api_key_client.post(v1("epics/"), {"name": "E"}, format="json")
    assert created.status_code == 201
    body = api_key_client.get(v1("epics/")).json()
    assert ENVELOPE <= body.keys()
    assert [r["id"] for r in body["results"]] == [created.json()["id"]]
    assert body["total_results"] == 1
    assert {"id", "name", "project", "workspace", "type_id"} <= body["results"][0].keys()


def test_create_accepts_a_normal_parent(api_key_client, v1, normal):
    r = api_key_client.post(v1("epics/"), {"name": "E", "parent": str(normal.id)}, format="json")
    assert r.status_code == 201


def test_create_with_a_form_encoded_body(api_key_client, v1):
    r = api_key_client.post(v1("epics/"), {"name": "E"})
    assert r.status_code == 201 and Issue.objects.get(pk=r.json()["id"]).type.is_epic


def test_external_id_lookup_is_for_epics_only(api_key_client, v1, normal_with_external_id):
    r = api_key_client.get(v1("epics/"), {"external_id": "x", "external_source": "y"})
    assert r.status_code == 404


def test_external_id_lookup_finds_an_epic(api_key_client, v1, project):
    epic = make_issue(project, "External epic", epic=True, external_id="x", external_source="y")
    r = api_key_client.get(v1("epics/"), {"external_id": "x", "external_source": "y"})
    assert r.status_code == 200 and r.json()["id"] == str(epic.id)


def test_detail_is_for_epics_only(api_key_client, v1, epic, normal):
    assert api_key_client.get(v1(f"epics/{epic.id}/")).status_code == 200
    assert api_key_client.get(v1(f"epics/{normal.id}/")).status_code == 404


def test_detail_does_not_take_writes(api_key_client, v1, epic):
    assert api_key_client.patch(v1(f"epics/{epic.id}/"), {"name": "x"}, format="json").status_code == 405
    assert api_key_client.delete(v1(f"epics/{epic.id}/")).status_code == 405


def test_children_list_and_add(api_key_client, v1, epic, normal):
    r = api_key_client.post(v1(f"epics/{epic.id}/issues/"), {"work_item_ids": [str(normal.id)]}, format="json")
    assert r.status_code == 200 and isinstance(r.json(), list)
    assert {"id", "name"} <= r.json()[0].keys()
    body = api_key_client.get(v1(f"epics/{epic.id}/issues/")).json()
    assert ENVELOPE <= body.keys()
    assert [c["id"] for c in body["results"]] == [str(normal.id)]


def test_children_list_includes_nested_epics(api_key_client, v1, epic, child_of_epic):
    nested = make_issue(epic.project, "Nested epic", epic=True, parent=epic)
    body = api_key_client.get(v1(f"epics/{epic.id}/issues/")).json()
    assert {c["id"] for c in body["results"]} == {str(child_of_epic.id), str(nested.id)}


def test_children_on_a_non_epic_is_404(api_key_client, v1, normal):
    assert api_key_client.get(v1(f"epics/{normal.id}/issues/")).status_code == 404


@pytest.mark.parametrize("bad", ["self", "ancestor", "other_project", "unknown", "not_a_uuid"])
def test_add_children_refuses_bad_ids(api_key_client, v1, nested_epics, bad):
    r = api_key_client.post(
        v1(f"epics/{nested_epics.inner.id}/issues/"),
        {"work_item_ids": [str(nested_epics.ids[bad]), str(nested_epics.good.id)]},
        format="json",
    )
    assert r.status_code == 400
    assert str(nested_epics.ids[bad]) in r.json()["ids"]
    nested_epics.good.refresh_from_db()
    assert nested_epics.good.parent_id is None  # all or nothing


@pytest.mark.parametrize("body", [{}, {"work_item_ids": []}, {"work_item_ids": "not-a-list"}])
def test_add_children_needs_ids(api_key_client, v1, epic, body):
    assert api_key_client.post(v1(f"epics/{epic.id}/issues/"), body, format="json").status_code == 400


def test_add_children_survives_an_existing_loop(api_key_client, v1, looped_epics, normal):
    r = api_key_client.post(
        v1(f"epics/{looped_epics.a.id}/issues/"), {"work_item_ids": [str(normal.id)]}, format="json"
    )
    assert r.status_code == 200


def test_add_children_records_activity(api_key_client, v1, epic, normal, child_of_epic, mock_activity):
    other = make_issue(epic.project, "Other epic", epic=True)
    ids = [str(normal.id), str(child_of_epic.id)]
    api_key_client.post(v1(f"epics/{other.id}/issues/"), {"work_item_ids": ids}, format="json")
    calls = {c.kwargs["issue_id"]: c.kwargs for c in mock_activity.call_args_list}
    assert calls.keys() == set(ids)
    assert all(c["type"] == "issue.activity.updated" for c in calls.values())
    assert calls[str(normal.id)]["current_instance"] == '{"parent": null}'
    assert calls[str(child_of_epic.id)]["current_instance"] == f'{{"parent": "{epic.id}"}}'


def test_work_item_can_take_an_epic_parent(api_key_client, v1, epic, normal):
    r = api_key_client.patch(v1(f"work-items/{normal.id}/"), {"parent": str(epic.id)}, format="json")
    assert r.status_code == 200
    normal.refresh_from_db()
    assert normal.parent_id == epic.id
