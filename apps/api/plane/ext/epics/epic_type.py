# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import transaction

from plane.db.models import Workspace
from plane.db.models.issue_type import IssueType, ProjectIssueType


def _find(workspace_id):
    return IssueType.objects.filter(workspace_id=workspace_id, is_epic=True).order_by("created_at").first()


def ensure_epic_type(project):
    """The workspace's epic type, created on first use and linked to the project."""
    issue_type = _find(project.workspace_id)
    if issue_type is None:
        with transaction.atomic():
            # no unique constraint on (workspace, is_epic): serialise first creates on the workspace row
            Workspace.objects.select_for_update().get(pk=project.workspace_id)
            issue_type = _find(project.workspace_id) or IssueType.objects.create(
                workspace_id=project.workspace_id,
                name="Epic",
                description="Epic",
                is_epic=True,
                is_default=False,
                level=1,
            )
    ProjectIssueType.objects.get_or_create(project=project, issue_type=issue_type, defaults={"level": 1})
    return issue_type
