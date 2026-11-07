# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Remove a built-in work item relation on the v1 API."""

import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.api.rate_limit import ApiKeyRateThrottle
from plane.app.serializers import IssueRelationSerializer
from plane.app.views.issue.relation import IssueRelationViewSet
from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import Issue, IssueRelation
from plane.utils.host import base_host
from plane.utils.issue_relation_mapper import get_inverse_relation


def _error(message, code):
    return Response({"error": message}, status=code)


class WorkItemRelationRemoveEndpoint(IssueRelationViewSet):
    authentication_classes = [APIKeyAuthentication]

    def get_throttles(self):
        return [ApiKeyRateThrottle()]

    def remove_relation(self, request, slug, project_id, issue_id):
        related_issue = request.data.get("related_issue")
        if not related_issue:
            return _error("related_issue is required", status.HTTP_400_BAD_REQUEST)
        try:
            related_issue = uuid.UUID(str(related_issue))
        except ValueError:
            return _error("related_issue must be a work item id", status.HTTP_400_BAD_REQUEST)
        if not Issue.objects.filter(pk=issue_id, project_id=project_id, workspace__slug=slug).exists():
            return _error("Work item not found", status.HTTP_404_NOT_FOUND)

        # a pair holds one row, so deleting it removes the relation from both items
        relation = IssueRelation.objects.filter(
            Q(issue_id=issue_id, related_issue_id=related_issue) | Q(issue_id=related_issue, related_issue_id=issue_id),
            workspace__slug=slug,
        ).first()
        if relation is None:
            return _error("No relation between these work items", status.HTTP_404_NOT_FOUND)

        # the activity names the type as seen from this item; the web app sends it, API callers needn't
        relation_type = (
            relation.relation_type
            if str(relation.issue_id) == str(issue_id)
            else get_inverse_relation(relation.relation_type)
        )
        current_instance = json.dumps(IssueRelationSerializer(relation).data, cls=DjangoJSONEncoder)
        relation.delete()
        issue_activity.delay(
            type="issue_relation.activity.deleted",
            requested_data=json.dumps(
                {"related_issue": str(related_issue), "relation_type": relation_type}, cls=DjangoJSONEncoder
            ),
            actor_id=str(request.user.id),
            issue_id=str(issue_id),
            project_id=str(project_id),
            current_instance=current_instance,
            epoch=int(timezone.now().timestamp()),
            notification=True,
            origin=base_host(request=request, is_app=True),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
