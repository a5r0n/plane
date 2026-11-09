# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""v1 activity routes that include comments and carry each activity's provenance."""

from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.response import Response

from plane.api.serializers import IssueActivitySerializer
from plane.api.views.issue import IssueActivityDetailAPIEndpoint, IssueActivityListAPIEndpoint
from plane.db.models import IssueActivity
from plane.ext.models import ActivityProvenance
from plane.utils.order_queryset import ACTIVITY_ORDER_BY_ALLOWLIST, sanitize_order_by

# upstream leaves comment, vote, reaction and draft out; we keep comments
HIDDEN_FIELDS = ["vote", "reaction", "draft"]


class ActivitySerializer(IssueActivitySerializer):
    provenance = serializers.SerializerMethodField()

    def get_provenance(self, activity):
        try:
            row = activity.squadron_provenance
        except ActivityProvenance.DoesNotExist:
            return None
        token = row.api_token
        if token and token.deleted_at:  # soft-deleted tokens never hit SET_NULL
            token = None
        return {
            "channel": row.channel,
            "token": {"id": str(token.id), "label": token.label} if token else None,
            "session": row.client_session or None,
            "agent": row.client_agent or None,
        }


def activities(request, slug, project_id, issue_id):
    return (
        IssueActivity.objects.filter(issue_id=issue_id, workspace__slug=slug, project_id=project_id)
        .filter(
            ~Q(field__in=HIDDEN_FIELDS),
            project__project_projectmember__member=request.user,
            project__project_projectmember__is_active=True,
        )
        .filter(project__archived_at__isnull=True)
        .select_related("actor", "workspace", "issue", "project", "squadron_provenance__api_token")
        .order_by(
            sanitize_order_by(request.GET.get("order_by", "created_at"), ACTIVITY_ORDER_BY_ALLOWLIST, "created_at")
        )
    )


class ActivityListAPIEndpoint(IssueActivityListAPIEndpoint):
    def get(self, request, slug, project_id, issue_id):
        return self.paginate(
            request=request,
            queryset=activities(request, slug, project_id, issue_id),
            on_results=lambda rows: ActivitySerializer(rows, many=True, fields=self.fields, expand=self.expand).data,
        )


class ActivityDetailAPIEndpoint(IssueActivityDetailAPIEndpoint):
    def get(self, request, slug, project_id, issue_id, pk):
        activity = activities(request, slug, project_id, issue_id).filter(id=pk).first()
        if not activity:
            return Response({"message": "Activity not found.", "code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        return Response(ActivitySerializer(activity, fields=self.fields, expand=self.expand).data)
