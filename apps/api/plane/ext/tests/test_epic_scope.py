# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta

import pytest
from django.db.models import Count
from django.utils import timezone

from plane.db.models import Cycle, CycleIssue, Issue, Module, ModuleIssue, Project
from plane.db.models.issue_type import IssueType, ProjectIssueType
from plane.ext.epics.epic_type import ensure_epic_type
from plane.ext.epics.scope import epic_scope
from plane.ext.tests.helpers import run_in_threads


def test_default_scope_shows_epics(epic, normal):
    assert set(Issue.issue_objects.values_list("id", flat=True)) == {epic.id, normal.id}


def test_exclude_hides_and_only_selects(epic, normal):
    with epic_scope("exclude"):
        assert list(Issue.issue_objects.values_list("id", flat=True)) == [normal.id]
    with epic_scope("only"):
        assert list(Issue.issue_objects.values_list("id", flat=True)) == [epic.id]


def test_scope_resets_after_an_exception(epic):
    with pytest.raises(ValueError), epic_scope("exclude"):
        raise ValueError
    assert Issue.issue_objects.filter(pk=epic.id).exists()


def test_unknown_scope_is_refused():
    with pytest.raises(ValueError), epic_scope("hide"):
        pass


def test_default_manager_is_unscoped(epic):
    with epic_scope("exclude"):
        assert Issue.objects.filter(pk=epic.id).exists()


def test_ensure_epic_type_is_idempotent_across_projects(project, other_project):
    first = ensure_epic_type(project)
    assert ensure_epic_type(project) == first
    assert ensure_epic_type(other_project) == first
    assert IssueType.objects.filter(workspace=project.workspace, is_epic=True).count() == 1
    assert ProjectIssueType.objects.filter(project=project, issue_type=first).count() == 1
    assert first.is_epic and first.level == 1 and not first.is_default


def test_ensure_epic_type_picks_the_oldest_when_duplicates_exist(project):
    newer = IssueType.objects.create(workspace=project.workspace, name="Epic", is_epic=True, level=1)
    older = IssueType.objects.create(workspace=project.workspace, name="Epic", is_epic=True, level=1)
    IssueType.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=2))  # auto_now_add
    assert newer != older
    assert ensure_epic_type(project) == older


@pytest.mark.django_db(transaction=True)
def test_two_first_creates_make_one_type(project):
    results = run_in_threads(2, lambda: ensure_epic_type(project).id)
    assert len(set(results)) == 1
    assert IssueType.objects.filter(workspace=project.workspace, is_epic=True).count() == 1


def test_exclude_drops_epics_from_counts_over_joins(project, epic, normal, create_user):
    common = {"project": project, "workspace": project.workspace}
    cycle = Cycle.objects.create(name="C", owned_by=create_user, **common)
    module = Module.objects.create(name="M", **common)
    for issue in (epic, normal):
        CycleIssue.objects.create(cycle=cycle, issue=issue, **common)
        ModuleIssue.objects.create(module=module, issue=issue, **common)

    def counts():
        return (
            Cycle.objects.annotate(n=Count("issue_cycle__issue__id")).get(pk=cycle.pk).n,
            Module.objects.annotate(n=Count("issue_module__issue__id")).get(pk=module.pk).n,
            Project.objects.annotate(n=Count("project_issue")).get(pk=project.pk).n,
        )

    assert counts() == (2, 2, 2)
    with epic_scope("exclude"):
        assert counts() == (1, 1, 1)
    with epic_scope("only"):
        assert counts() == (2, 2, 2)


def test_exclude_counts_everything_when_no_epic_type_exists(project, normal):
    with epic_scope("exclude"):
        assert Project.objects.annotate(n=Count("project_issue")).get(pk=project.pk).n == 1
