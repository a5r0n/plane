# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta

import pytest
from django.utils import timezone

from plane.db.models import Cycle, CycleIssue, Module, ModuleIssue
from plane.ext.epics import routes

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_celery(monkeypatch):
    monkeypatch.setattr("celery.app.task.Task.delay", lambda *a, **k: None)


@pytest.fixture
def cycle(project, create_user):
    now = timezone.now()
    return Cycle.objects.create(
        name="Sprint",
        project=project,
        workspace=project.workspace,
        owned_by=create_user,
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=7),
    )


@pytest.fixture
def module(project):
    return Module.objects.create(name="Mod", project=project, workspace=project.workspace)


def assert_refused(r, epic, target):
    assert r.status_code == 400, r.content
    assert r.json() == {"error": f"An epic can't be added to a {target}.", "ids": [str(epic.id)]}


def test_session_cycle_refuses_an_epic(session_client, url, cycle, epic, normal):
    r = session_client.post(
        url(f"cycles/{cycle.id}/cycle-issues/"), {"issues": [str(normal.id), str(epic.id)]}, format="json"
    )
    assert_refused(r, epic, "cycle")
    assert not CycleIssue.objects.filter(cycle=cycle).exists()


def test_session_cycle_still_takes_work_items(session_client, url, cycle, normal, child_of_epic):
    r = session_client.post(
        url(f"cycles/{cycle.id}/cycle-issues/"), {"issues": [str(normal.id), str(child_of_epic.id)]}, format="json"
    )
    assert r.status_code == 201, r.content
    assert CycleIssue.objects.filter(cycle=cycle).count() == 2


def test_session_module_refuses_an_epic(session_client, url, module, epic):
    r = session_client.post(url(f"modules/{module.id}/issues/"), {"issues": [str(epic.id)]}, format="json")
    assert_refused(r, epic, "module")
    assert not ModuleIssue.objects.filter(module=module).exists()


def test_session_item_modules_refuses_an_epic(session_client, url, module, epic):
    r = session_client.post(url(f"issues/{epic.id}/modules/"), {"modules": [str(module.id)]}, format="json")
    assert_refused(r, epic, "module")
    assert not ModuleIssue.objects.filter(module=module).exists()


def test_session_item_modules_lets_an_epic_leave(session_client, url, module, epic):
    ModuleIssue.objects.create(module=module, issue=epic, project=epic.project, workspace=epic.workspace)
    r = session_client.post(
        url(f"issues/{epic.id}/modules/"), {"modules": [], "removed_modules": [str(module.id)]}, format="json"
    )
    assert r.status_code == 201, r.content
    assert not ModuleIssue.objects.filter(module=module).exists()


def test_session_item_modules_still_takes_work_items(session_client, url, module, normal):
    r = session_client.post(url(f"issues/{normal.id}/modules/"), {"modules": [str(module.id)]}, format="json")
    assert r.status_code == 201, r.content
    assert ModuleIssue.objects.filter(module=module, issue=normal).exists()


def test_v1_cycle_refuses_an_epic(api_key_client, v1, cycle, epic):
    r = api_key_client.post(v1(f"cycles/{cycle.id}/cycle-issues/"), {"issues": [str(epic.id)]}, format="json")
    assert_refused(r, epic, "cycle")
    assert not CycleIssue.objects.filter(cycle=cycle).exists()


def test_v1_module_refuses_an_epic(api_key_client, v1, module, epic, normal):
    r = api_key_client.post(v1(f"modules/{module.id}/module-issues/"), {"issues": [str(epic.id)]}, format="json")
    assert_refused(r, epic, "module")
    r = api_key_client.post(v1(f"modules/{module.id}/module-issues/"), {"issues": [str(normal.id)]}, format="json")
    assert r.status_code == 200, r.content  # upstream answers 200 here
    assert ModuleIssue.objects.filter(module=module, issue=normal).exists()


def test_v1_cycle_lists_still_work(api_key_client, v1, cycle, normal):
    CycleIssue.objects.create(cycle=cycle, issue=normal, project=normal.project, workspace=normal.workspace)
    r = api_key_client.get(v1(f"cycles/{cycle.id}/cycle-issues/"))
    assert r.status_code == 200, r.content


def test_anonymous_gets_no_answer_about_epics(api_client, v1, cycle, epic):
    r = api_client.post(v1(f"cycles/{cycle.id}/cycle-issues/"), {"issues": [str(epic.id)]}, format="json")
    assert r.status_code in (401, 403)


def test_every_refused_route_exists():
    from plane.ext.epics.urls import route_table

    table = route_table()
    assert routes.REFUSE.keys() <= table.keys()
