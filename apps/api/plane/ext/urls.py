# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.ext.epics.urls import epic_patterns
from plane.ext.pages import ProjectPageAPIEndpoint
from plane.ext.properties import PropertyDetailEndpoint, PropertyListCreateEndpoint
from plane.ext.relations import WorkItemRelationRemoveEndpoint
from plane.ext.search import WorkItemSearchEndpoint
from plane.ext.steps import (
    StepDetailEndpoint,
    StepListCreateEndpoint,
    StepReorderEndpoint,
    StepSetPathEndpoint,
    WorkItemByIdentifierAPIEndpoint,
    WorkItemDetailAPIEndpoint,
)
from plane.ext.work_items import WorkItemListCreateAPIEndpoint

PROJECT = "v1/workspaces/<str:slug>/projects/<uuid:project_id>/"
PAGES = PROJECT + "pages/"
ITEMS = ("work-items", "issues")


def step_patterns():
    """Steps under both item prefixes, plus the item reads that can return them."""
    for items in ITEMS:
        item = f"{PROJECT}{items}/<uuid:issue_id>/"
        steps = item + "steps/"
        yield path(steps, StepListCreateEndpoint.as_view(), name=f"squadron-{items}-steps")
        yield path(steps + "set-path/", StepSetPathEndpoint.as_view(), name=f"squadron-{items}-steps-set-path")
        yield path(steps + "reorder/", StepReorderEndpoint.as_view(), name=f"squadron-{items}-steps-reorder")
        yield path(steps + "<uuid:step_id>/", StepDetailEndpoint.as_view(), name=f"squadron-{items}-step")
        yield path(
            f"{PROJECT}{items}/<uuid:pk>/",
            WorkItemDetailAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
            name=f"squadron-{items}-detail",
        )
        yield path(
            f"v1/workspaces/<str:slug>/{items}/<str:project_identifier>-<str:issue_identifier>/",
            WorkItemByIdentifierAPIEndpoint.as_view(http_method_names=["get"]),
            name=f"squadron-{items}-by-identifier",
        )


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
    *step_patterns(),
    path(
        PROJECT + "properties/",
        PropertyListCreateEndpoint.as_view(http_method_names=["get", "post"]),
        name="squadron-properties",
    ),
    path(
        PROJECT + "properties/<uuid:property_id>/",
        PropertyDetailEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="squadron-property",
    ),
]

# epic routes and list shadows resolve before ours and upstream's
urlpatterns = epic_patterns(urlpatterns) + urlpatterns
