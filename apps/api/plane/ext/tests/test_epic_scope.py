# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta

import pytest
from django.utils import timezone

from plane.db.models import Issue
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
