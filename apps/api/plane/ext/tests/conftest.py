# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from types import SimpleNamespace

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
from plane.db.models import Issue, IssueActivity, IssueComment, Project, ProjectMember, State
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
