# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
import uuid

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from plane.api.serializers import IssueSerializer as APIIssueSerializer
from plane.api.views.base import BaseAPIView
from plane.api.views.issue import IssueDetailAPIEndpoint, IssueListCreateAPIEndpoint
from plane.api.views.project import ProjectSummaryAPIEndpoint
from plane.app.permissions import ROLE, ProjectEntityPermission, allow_permission
from plane.bgtasks.issue_activities_task import issue_activity
from plane.app.views.issue.base import IssueViewSet
from plane.db.models import Issue, Project, StateGroup
from plane.ext.epics.epic_type import ensure_epic_type
from plane.ext.epics.scope import current_scope, epic_scope
from plane.ext.properties import CustomFieldsMixin, with_values
from plane.utils.host import base_host


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


class ProjectSummaryEndpoint(ProjectSummaryAPIEndpoint):
    """Upstream counts issues on the bare table, past the scope; take the epics back out."""

    def _get_all_summary_counts(self, project_id, requested_fields):
        counts = super()._get_all_summary_counts(project_id, requested_fields)
        if "issues" in counts and current_scope() == "exclude":
            epics = Issue.objects.filter(project_id=project_id, type__is_epic=True)
            counts["issues"] -= epics.exclude(state__group=StateGroup.TRIAGE.value).count()
        return counts


def get_epic(slug, project_id, pk):
    return get_object_or_404(
        Issue.issue_objects, pk=pk, project_id=project_id, workspace__slug=slug, type__is_epic=True
    )


class EpicListCreateAPIEndpoint(CustomFieldsMixin, IssueListCreateAPIEndpoint):
    """v1 work item list and create, for epics only."""

    def get_queryset(self):
        with epic_scope("all"):  # built in all, so sub_issues_count counts every child
            return super().get_queryset().filter(type__is_epic=True)

    def get(self, request, slug, project_id):
        external_id, external_source = request.GET.get("external_id"), request.GET.get("external_source")
        if external_id and external_source:
            found = Issue.objects.filter(
                external_id=external_id, external_source=external_source, workspace__slug=slug, project_id=project_id
            )
            if not found.filter(type__is_epic=True).exists():
                return Response({"error": "The requested resource does not exist."}, status=status.HTTP_404_NOT_FOUND)
        with epic_scope("only"):  # the total count, which upstream takes from the manager
            return super().get(request, slug, project_id)

    def post(self, request, slug, project_id):
        project = get_object_or_404(Project, pk=project_id, workspace__slug=slug)
        stamp_type(request, "type_id", ensure_epic_type(project).id)
        return super().post(request, slug, project_id)


class EpicDetailAPIEndpoint(CustomFieldsMixin, IssueDetailAPIEndpoint):
    def get(self, request, slug, project_id, pk):
        get_epic(slug, project_id, pk)
        return super().get(request, slug, project_id, pk)


def ancestors(issue):
    """Ids above an item, stopping at a loop the session routes may already have made."""
    seen, parent_id = set(), issue.parent_id
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent_id = Issue.objects.filter(pk=parent_id).values_list("parent_id", flat=True).first()
    return seen


def as_uuid(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


class EpicChildrenAPIEndpoint(BaseAPIView):
    """An epic's children: list them, or adopt work items as children."""

    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id, pk):
        epic = get_epic(slug, project_id, pk)
        children = Issue.issue_objects.filter(parent_id=epic.id, project_id=project_id).order_by("-created_at")
        return self.paginate(
            request=request,
            queryset=children,
            on_results=lambda rows: with_values(
                APIIssueSerializer(rows, many=True, fields=self.fields, expand=self.expand).data
            ),
        )

    def post(self, request, slug, project_id, pk):
        epic = get_epic(slug, project_id, pk)
        sent = request.data.get("work_item_ids")
        if not isinstance(sent, list) or not sent:
            return Response({"error": "work_item_ids must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)
        ids = {str(value): as_uuid(value) for value in sent}
        bad = sorted(value for value, parsed in ids.items() if parsed is None)
        if bad:
            return Response({"error": "not a work item id", "ids": bad}, status=status.HTTP_400_BAD_REQUEST)
        wanted = set(ids.values())
        children = list(Issue.issue_objects.filter(pk__in=wanted, project_id=project_id, workspace__slug=slug))
        missing = sorted(str(i) for i in wanted - {child.id for child in children})
        if missing:
            return Response(
                {"error": "not a work item in this project", "ids": missing}, status=status.HTTP_400_BAD_REQUEST
            )
        above = sorted(str(i) for i in wanted & ({epic.id} | ancestors(epic)))
        if above:
            return Response(
                {"error": "the epic itself or one of its parents", "ids": above}, status=status.HTTP_400_BAD_REQUEST
            )

        previous = {child.id: child.parent_id for child in children}
        for child in children:
            child.parent_id = epic.id
        Issue.objects.bulk_update(children, ["parent"])
        for child in children:
            issue_activity.delay(
                type="issue.activity.updated",
                requested_data=json.dumps({"parent": str(epic.id)}),
                actor_id=str(request.user.id),
                issue_id=str(child.id),
                project_id=str(project_id),
                current_instance=json.dumps({"parent": str(previous[child.id]) if previous[child.id] else None}),
                epoch=int(timezone.now().timestamp()),
                notification=True,
                origin=base_host(request=request, is_app=True),
            )
        rows = Issue.issue_objects.filter(pk__in=wanted).order_by("-created_at")
        return Response(APIIssueSerializer(rows, many=True).data, status=status.HTTP_200_OK)
