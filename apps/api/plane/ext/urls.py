# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.ext.pages import ProjectPageAPIEndpoint

PAGES = "v1/workspaces/<str:slug>/projects/<uuid:project_id>/pages/"

urlpatterns = [
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
]
