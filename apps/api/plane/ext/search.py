# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Work item search on the v1 API that also matches descriptions and comments."""

import re

from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When
from rest_framework import status
from rest_framework.response import Response

from plane.api.views.issue import IssueSearchEndpoint
from plane.db.models import Issue, IssueComment

# match tiers, best first; a result reports the best tier it hit
TITLE, DESCRIPTION, COMMENT = 0, 1, 2
MATCHED = {TITLE: "title", DESCRIPTION: "description", COMMENT: "comment"}


class WorkItemSearchEndpoint(IssueSearchEndpoint):
    def get(self, request, slug):
        query = request.query_params.get("search", False)
        limit = request.query_params.get("limit", 10)
        workspace_search = request.query_params.get("workspace_search", "false")
        project_id = request.query_params.get("project_id", False)

        if not query:
            return Response({"issues": []}, status=status.HTTP_200_OK)

        # upstream's matches: name, project identifier, whole-number sequence ids
        title_q = Q(name__icontains=query) | Q(project__identifier__icontains=query)
        for sequence_id in re.findall(r"\b\d+\b", query):
            title_q |= Q(sequence_id=sequence_id)
        description_q = Q(description_stripped__icontains=query)
        # default manager skips soft-deleted comments
        comment_q = Q(Exists(IssueComment.objects.filter(issue_id=OuterRef("pk"), comment_stripped__icontains=query)))

        issues = Issue.issue_objects.filter(
            title_q | description_q | comment_q,
            project__project_projectmember__member=self.request.user,
            project__project_projectmember__is_active=True,
            project__archived_at__isnull=True,
            workspace__slug=slug,
        )

        if workspace_search == "false" and project_id:
            issues = issues.filter(project_id=project_id)

        issue_results = (
            issues.annotate(
                match_rank=Case(
                    When(title_q, then=Value(TITLE)),
                    When(description_q, then=Value(DESCRIPTION)),
                    default=Value(COMMENT),
                    output_field=IntegerField(),
                )
            )
            .order_by("match_rank", "-created_at")
            .distinct()
            .values(
                "name",
                "id",
                "sequence_id",
                "project__identifier",
                "project_id",
                "workspace__slug",
                "match_rank",
                "created_at",
            )[: int(limit)]
        )

        results = [
            {
                "name": r["name"],
                "id": r["id"],
                "sequence_id": r["sequence_id"],
                "project__identifier": r["project__identifier"],
                "project_id": r["project_id"],
                "workspace__slug": r["workspace__slug"],
                "matched": MATCHED[r["match_rank"]],
            }
            for r in issue_results
        ]
        return Response({"issues": results}, status=status.HTTP_200_OK)
