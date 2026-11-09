# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Epic routes generated from upstream's own, plus the shadows that hide epics from lists."""

import functools
from importlib import import_module

from django.urls import URLResolver, path
from django.urls.resolvers import RoutePattern

from plane.db.models import Issue
from plane.ext.epics import routes
from plane.ext.epics.refuse import refusing
from plane.ext.epics.scope import epic_scope
from plane.ext.epics.views import (
    EpicChildrenAPIEndpoint,
    EpicDetailAPIEndpoint,
    EpicListCreateAPIEndpoint,
    EpicViewSet,
    ProjectSummaryEndpoint,
)

# url modules in the order plane/urls.py mounts them under api/
SOURCES = (("", "plane.app.urls"), ("public/", "plane.space.urls"), ("v1/", "plane.api.urls"))

# hidden routes whose upstream view counts past the scope: route -> the view that doesn't
REPLACED = {routes.V1 + routes.P + "summary/": ProjectSummaryEndpoint.as_view()}


def walk(patterns, prefix=""):
    """(full route, URLPattern) for every route pattern, recursively."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern.pattern, RoutePattern):
            yield prefix + str(pattern.pattern), pattern


def route_table(own=()):
    """Full route -> the pattern Django resolves first: ours, then upstream's."""
    table = {}
    for route, pattern in walk(own):
        table.setdefault(route, pattern)
    for prefix, module in SOURCES:
        for route, pattern in walk(import_module(module).urlpatterns, prefix):
            table.setdefault(route, pattern)
    return table


def render_in_scope(response):
    # Django renders after the view returns; a lazy queryset would escape the scope
    return response.render() if hasattr(response, "render") and not response.is_rendered else response


def _issue_rows(data, found):
    if isinstance(data, dict):
        if "id" in data and "sequence_id" in data:
            found.append(data)
        for value in data.values():
            _issue_rows(value, found)
    elif isinstance(data, list):
        for value in data:
            _issue_rows(value, found)
    return found


def mark_epics(response):
    """Add is_epic to every issue row; the web app reads it to pick the epic view. Runs before render."""
    if getattr(response, "status_code", 500) not in (200, 201) or not hasattr(response, "data"):
        return response
    rows = _issue_rows(response.data, [])
    if rows:
        epic_ids = {
            str(pk)
            for pk in Issue.objects.filter(pk__in={str(r["id"]) for r in rows}, type__is_epic=True).values_list(
                "pk", flat=True
            )
        }
        for row in rows:
            row["is_epic"] = str(row["id"]) in epic_ids
    return response


def alias_activity_type(request):
    """The web app sends activity_type=epic-*; upstream's history view only knows issue-*."""
    sent = request.GET.get("activity_type")
    if sent in routes.ACTIVITY_TYPES:
        request.GET = request.GET.copy()
        request.GET["activity_type"] = routes.ACTIVITY_TYPES[sent]


def scoped(view, mode, mark=False):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        alias_activity_type(request)
        with epic_scope(mode):
            response = view(request, *args, **kwargs)
            if mark and request.method in ("GET", "POST"):
                mark_epics(response)
            return render_in_scope(response)

    return wrapper


def hide_get(view, route):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        hidden = request.method == "GET" and route in routes.HIDE  # read per request, for the sweep's control run
        if route == routes.SEARCH_ISSUES and request.GET.get("issue_id"):
            hidden = False  # parent lookup by id, which may be an epic
        with epic_scope("exclude" if hidden else "all"):
            return render_in_scope(view(request, *args, **kwargs))

    return wrapper


def alias_patterns(table=None):
    table = table or route_table()
    return [
        path(epic, scoped(table[source].callback, "all"), name=f"squadron-epic-{table[source].name}")
        for source, epic in routes.ALIASES.items()
    ]


def epic_patterns(own=()):
    """Every epic route and shadow; mount these before `own` and upstream's routes."""
    table = route_table(own)
    patterns = [
        path(
            routes.P + "epics/",
            scoped(EpicViewSet.as_view({"get": "list", "post": "create"}), "all", mark=True),
            name="squadron-epics",
        ),
        path(routes.V1 + routes.P + "epics/", EpicListCreateAPIEndpoint.as_view(), name="squadron-v1-epics"),
        path(
            routes.V1 + routes.P + "epics/<uuid:pk>/",
            EpicDetailAPIEndpoint.as_view(http_method_names=["get"]),
            name="squadron-v1-epic",
        ),
        path(
            routes.V1 + routes.P + "epics/<uuid:pk>/issues/",
            EpicChildrenAPIEndpoint.as_view(),
            name="squadron-v1-epic-issues",
        ),
        *alias_patterns(table),
    ]
    patterns += [
        path(route, scoped(table[route].callback, "all", mark=True), name=f"squadron-marked-{table[route].name}")
        for route in routes.MARKED
    ]
    patterns += [
        path(route, hide_get(own_view(table, route), route), name=f"hide-{table[route].name}")
        for route in sorted(routes.HIDE)
    ]
    patterns += [
        path(route, own_view(table, route), name=f"refuse-{table[route].name}")
        for route in sorted(routes.REFUSE.keys() - routes.HIDE)
    ]
    return patterns


def own_view(table, route):
    view = REPLACED.get(route, table[route].callback)
    return refusing(view, routes.REFUSE[route]) if route in routes.REFUSE else view
