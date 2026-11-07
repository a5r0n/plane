# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.ext.epics.urls import epic_patterns
from plane.ext.pages import ProjectPageAPIEndpoint
from plane.ext.relations import WorkItemRelationRemoveEndpoint
from plane.ext.search import WorkItemSearchEndpoint
from plane.ext.work_items import WorkItemListCreateAPIEndpoint

PROJECT = "v1/workspaces/<str:slug>/projects/<uuid:project_id>/"
PAGES = PROJECT + "pages/"

urlpatterns = [
    *(
        path(
            PROJECT + tail,
            WorkItemListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
            name=f"squadron-{tail.strip('/')}-list",
        )
        for tail in ("work-items/", "issues/")
    ),
    path(PAGES, ProjectPageAPIEndpoint.as_view({"get": "list", "post": "create"}), name="squadron-project-pages"),
    path(
        PAGES + "<uuid:page_id>/",
        ProjectPageAPIEndpoint.as_view(
            {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
        ),
        name="squadron-project-page",
    ),
    path(
        PAGES + "<uuid:page_id>/archive/",
        ProjectPageAPIEndpoint.as_view({"post": "archive", "delete": "unarchive"}),
        name="squadron-project-page-archive",
    ),
    path(
        "v1/workspaces/<str:slug>/work-items/search/",
        WorkItemSearchEndpoint.as_view(http_method_names=["get"]),
        name="squadron-work-item-search",
    ),
    path(
        "v1/workspaces/<str:slug>/issues/search/",
        WorkItemSearchEndpoint.as_view(http_method_names=["get"]),
        name="squadron-issue-search",
    ),
    path(
        "v1/workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/relations/remove/",
        WorkItemRelationRemoveEndpoint.as_view({"post": "remove_relation"}),
        name="squadron-work-item-relation-remove",
    ),
]

# epic routes and list shadows resolve before ours and upstream's
urlpatterns = epic_patterns(urlpatterns) + urlpatterns
