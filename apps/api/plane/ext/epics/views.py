# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.shortcuts import get_object_or_404

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.issue.base import IssueViewSet
from plane.db.models import Project
from plane.ext.epics.epic_type import ensure_epic_type


def stamp_type(request, field, value):
    """Set one field on the request body without mutating it; a form body's QueryDict is immutable."""
    data = request.data.copy()
    data[field] = str(value)
    request._full_data = data  # DRF's request.data returns this once loaded


class EpicViewSet(IssueViewSet):
    """Work item behaviour; lists only epics, and create stamps the epic type."""

    def get_queryset(self):
        return super().get_queryset().filter(type__is_epic=True)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])  # upstream's check, run before the project lookup
    def create(self, request, slug, project_id):
        project = get_object_or_404(Project, pk=project_id, workspace__slug=slug)
        stamp_type(request, "type", ensure_epic_type(project).id)
        return super().create(request, slug=slug, project_id=project_id)
