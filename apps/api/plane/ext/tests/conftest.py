# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

import pytest

# reuse the upstream suite's fixtures, which only apply under plane/tests
from plane.tests.conftest import (  # noqa: F401
    api_client,
    api_key_client,
    api_token,
    create_user,
    session_client,
    user_data,
    workspace,
)
from rest_framework.test import APIClient
from rest_framework.throttling import AnonRateThrottle

from plane.db.models import (
    AnalyticView,
    Cycle,
    CycleIssue,
    DeployBoard,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueComment,
    Module,
    ModuleIssue,
    Project,
    ProjectMember,
    State,
)
from plane.ext.epics.epic_type import ensure_epic_type


def make_project(workspace, user, name, identifier):
    project = Project.objects.create(name=name, identifier=identifier, workspace=workspace, created_by=user)
    ProjectMember.objects.create(project=project, member=user, role=20, is_active=True)
    State.objects.create(name="Todo", project=project, workspace=workspace, group="backlog", default=True)
    return project


def make_issue(project, name, epic=False, **fields):
    if epic:
        fields["type"] = ensure_epic_type(project)
    return Issue.objects.create(name=name, project=project, workspace=project.workspace, **fields)


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Epics", "EP")


@pytest.fixture
def other_project(db, workspace, create_user):
    return make_project(workspace, create_user, "Other", "OT")


@pytest.fixture
def epic(project):
    return make_issue(project, "Epic one", epic=True)


@pytest.fixture
def normal(project):
    return make_issue(project, "Normal one")


@pytest.fixture
def child_of_epic(project, epic):
    return make_issue(project, "Child one", parent=epic)


@pytest.fixture
def done_state(project):
    return State.objects.create(name="Done", project=project, workspace=project.workspace, group="completed")


completed_state = done_state


@pytest.fixture
def url(workspace, project):
    return lambda tail: f"/api/workspaces/{workspace.slug}/projects/{project.id}/{tail}"


@pytest.fixture
def v1(workspace, project):
    return lambda tail: f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/{tail}"


@pytest.fixture
def epic_with_history(epic, create_user):
    activity = IssueActivity.objects.create(
        issue=epic, project=epic.project, workspace=epic.workspace, actor=create_user, verb="updated", field="name"
    )
    comment = IssueComment.objects.create(
        issue=epic, project=epic.project, workspace=epic.workspace, actor=create_user, comment_html="<p>x</p>"
    )
    return SimpleNamespace(epic=epic, activity=activity, comment=comment)


class World:
    """A bare project with one of everything a list can hold; add_epic() adds the epic to all of it."""

    def __init__(self, workspace, user):
        self.workspace, self.user = workspace, user
        self.project = make_project(workspace, user, "Sweep", "SW")
        self.normal = make_issue(self.project, "Sweep normal")
        self.child = make_issue(self.project, "Sweep child")
        now = timezone.now()
        self.cycle = Cycle.objects.create(
            name="Sweep cycle",
            project=self.project,
            workspace=workspace,
            owned_by=user,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=7),
        )
        self.module = Module.objects.create(name="Sweep module", project=self.project, workspace=workspace)
        self.board = DeployBoard.objects.create(
            entity_name="project", entity_identifier=self.project.id, project=self.project, workspace=workspace
        )
        self.anchor = self.board.anchor
        self.analytic = AnalyticView.objects.create(
            workspace=workspace,
            name="Sweep analytic",
            query={"project_id": str(self.project.id)},
            query_dict={"x_axis": "state_id", "y_axis": "issue_count"},
        )
        self.epic = None
        self._attach(self.normal)  # not the child: its new parent would move cycle and module sub-issue counts

    @property
    def epic_id(self):
        return str(self.epic.id) if self.epic else None

    def _attach(self, issue):
        common = {"project": self.project, "workspace": self.workspace}
        CycleIssue.objects.create(cycle=self.cycle, issue=issue, **common)
        ModuleIssue.objects.create(module=self.module, issue=issue, **common)
        IssueAssignee.objects.create(issue=issue, assignee=self.user, **common)

    def add_epic(self):
        if self.epic is None:
            self.epic = make_issue(self.project, "Sweep epic", epic=True)
            self._attach(self.epic)
            Issue.objects.filter(pk=self.child.pk).update(parent=self.epic)
        return self.epic

    def value(self, route, token, name):
        before = route.split(token)[0].rstrip("/").split("/")[-1]
        if before == "epics":
            return self.epic_id
        item = {"issues": self.normal, "work-items": self.normal, "issues-detail": self.normal}
        by_segment = {"cycles": self.cycle, "modules": self.module, "projects": self.project, **item}
        if name == "pk":
            obj = by_segment.get(before)
            return obj.id if obj else None
        return {
            "slug": self.workspace.slug,
            "project_id": self.project.id,
            "cycle_id": self.cycle.id,
            "analytic_id": self.analytic.id,
            "module_id": self.module.id,
            "anchor": self.anchor,
            "user_id": self.user.id,
            "issue_id": self.normal.id,
            "work_item_id": self.normal.id,
            "project_identifier": self.project.identifier,
            "issue_identifier": self.normal.sequence_id,
        }.get(name)


@pytest.fixture
def world(db, workspace, create_user):
    return World(workspace, create_user)


@pytest.fixture
def clients(create_user, api_token, monkeypatch):
    monkeypatch.setattr(AnonRateThrottle, "allow_request", lambda self, request, view: True)
    monkeypatch.setattr("celery.app.task.Task.delay", lambda *a, **k: None)
    session, api_key, anon = APIClient(), APIClient(), APIClient()
    session.force_authenticate(user=create_user)
    api_key.credentials(HTTP_X_API_KEY=api_token.token)
    for client in (session, api_key, anon):
        client.raise_request_exception = False
    return SimpleNamespace(session=session, api_key=api_key, anon=anon)
