# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The v1 project work item list, with `pql` filtering (plane.ext.pql) and custom_fields on top of upstream's."""

from rest_framework import status
from rest_framework.response import Response

from plane.api.views.issue import IssueListCreateAPIEndpoint
from plane.ext.pql import Context, PQLError, compile_pql
from plane.ext.properties import CustomFieldsMixin


class WorkItemListCreateAPIEndpoint(CustomFieldsMixin, IssueListCreateAPIEndpoint):
    pql_q = None

    def get(self, request, slug, project_id):
        pql = request.GET.get("pql")
        if pql:
            try:
                self.pql_q = compile_pql(pql, Context(user_id=request.user.id, workspace_slug=slug))
            except PQLError as exc:
                return Response({"pql": f"Invalid PQL: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
            # upstream refuses any pql; it has been compiled, so hand upstream the rest
            query = request._request.GET.copy()
            query.pop("pql")
            request._request.GET = query
        return super().get(request, slug, project_id)

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(self.pql_q) if self.pql_q is not None else queryset

    def paginate(self, *args, total_count_queryset=None, **kwargs):
        if self.pql_q is not None and total_count_queryset is not None:
            total_count_queryset = total_count_queryset.filter(self.pql_q)
        return super().paginate(*args, total_count_queryset=total_count_queryset, **kwargs)
