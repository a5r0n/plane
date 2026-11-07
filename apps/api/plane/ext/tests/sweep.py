# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Walk every GET route under api/ and report where an epic shows up: as a row, or in a number."""

import json
import re
from dataclasses import dataclass, field

from django.urls import URLResolver, get_resolver
from django.urls.resolvers import RoutePattern

from plane.ext.epics import routes
from plane.ext.tests.helpers import row_ids

PARAM = re.compile(r"<(?:\w+:)?(\w+)>")
VOLATILE = {"sequence_id", "sort_order", "sequence"}
P, W = routes.P, routes.W


@dataclass
class Variant:
    query: dict
    leak_check: bool = True


GROUPED = [{}, {"group_by": "state_id"}, {"group_by": "state_id", "sub_group_by": "priority"}]
SEARCH = "Sweep epic"


def query_variants(route, world):
    """Requests to send per route; one bare GET when a route has none."""
    grouped = [Variant(q) for q in GROUPED]
    search = [Variant({"search": SEARCH})]
    table = {
        P + "issues/": grouped,
        W + "issues/": grouped,
        P + "cycles/<uuid:cycle_id>/cycle-issues/": grouped,
        P + "modules/<uuid:module_id>/issues/": grouped,
        P + "issues/list/": [Variant({"issues": f"{world.epic_id},{world.normal.id}"})],
        P + "search-issues/": [
            Variant({"search": SEARCH}),
            Variant({"search": SEARCH, "issue_id": str(world.normal.id)}, leak_check=False),
        ],
        W + "search/": search,
        "v1/" + W + "work-items/search/": search,
        "v1/" + W + "issues/search/": search,
        W + "entity-search/": [Variant({"query": SEARCH, "query_type": "issue"})],
        W + "analytics/": [
            Variant({"x_axis": "state_id", "y_axis": "issue_count"}),
            Variant({"x_axis": "priority", "y_axis": "issue_count", "segment": "assignees__id"}),
        ],
        W + "advance-analytics/": [Variant({"tab": tab}) for tab in ("overview", "work-items")],
        W + "advance-analytics-charts/": [
            Variant({"type": t}) for t in ("projects", "custom-work-items", "work-items")
        ],
        P + "advance-analytics-charts/": [
            Variant({"type": "custom-work-items"}),
            Variant({"type": "work-items"}),
            Variant({"type": "work-items", "cycle_id": str(world.cycle.id)}),
            Variant({"type": "work-items", "module_id": str(world.module.id)}),
        ],
    }
    return table.get(route, [Variant({})])


def walk(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern.pattern, RoutePattern):
            yield prefix + str(pattern.pattern), pattern.callback


def accepts_get(callback):
    if getattr(callback, "actions", None) is not None:
        return "get" in callback.actions
    view_class = getattr(callback, "view_class", None)
    if view_class is None:
        return True
    allowed = (getattr(callback, "initkwargs", None) or {}).get("http_method_names", view_class.http_method_names)
    return hasattr(view_class, "get") and "get" in allowed


def get_routes():
    """Full pattern relative to api/ -> the callback Django resolves first."""
    found = {}
    for route, callback in walk(get_resolver().url_patterns):
        if not route.startswith("api/") or route.startswith("api/instances/"):
            continue
        found.setdefault(route[len("api/") :], callback)
    return {route: cb for route, cb in found.items() if accepts_get(cb) and route not in routes.SKIP}


def client_for(clients, route):
    if route.startswith("v1/"):
        return clients.api_key
    if route.startswith("public/"):
        return clients.anon
    return clients.session


def fill(route, world):
    """The concrete path, or None when a param can't be filled."""
    out = route
    for match in PARAM.finditer(route):
        value = world.value(route, match.group(0), match.group(1))
        if value is None:
            return None
        out = out.replace(match.group(0), str(value), 1)
    return "/api/" + out


def numbers(data, epic_id, path=""):
    """Every number in the body, keyed by a path that names list rows by id."""
    out = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if key in VOLATILE or (epic_id and key == epic_id):
                continue
            out.update(numbers(value, epic_id, f"{path}/{key}"))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            key = value.get("id") if isinstance(value, dict) else None
            if epic_id and key == epic_id:
                continue
            out.update(numbers(value, epic_id, f"{path}/{'#' + str(key) if key else index}"))
    elif isinstance(data, (int, float)) and not isinstance(data, bool):
        out[path] = data
    return out


def bare_ids(data, found=None):
    """Strings in lists anywhere, for routes that return bare id lists."""
    found = set() if found is None else found
    if isinstance(data, dict):
        for value in data.values():
            bare_ids(value, found)
    elif isinstance(data, list):
        for value in data:
            if isinstance(value, str):
                found.add(value)
            else:
                bare_ids(value, found)
    return found


def leaks(response, epic_id):
    try:
        body = response.json()
    except (ValueError, TypeError):
        return epic_id in response.content.decode(errors="replace")
    return epic_id in row_ids(body) or epic_id in bare_ids(body)


def get_route(clients, world, route, query=None):
    """One GET on a full pattern; returns the JSON body."""
    response = client_for(clients, route).get(fill(route, world), query or {})
    assert response.status_code == 200, (route, response.status_code)
    return response.json()


@dataclass
class Report:
    walked: set = field(default_factory=set)
    leaks: set = field(default_factory=set)
    not_exercised: set = field(default_factory=set)
    count_changes: dict = field(default_factory=dict)
    numbers: dict = field(default_factory=dict)
    statuses: dict = field(default_factory=dict)


def sweep(world, clients, baseline=None):
    report = Report()
    epic_id = world.epic_id
    for route in sorted(get_routes()):
        report.walked.add(route)
        path = fill(route, world)
        if path is None:
            report.not_exercised.add(route)
            continue
        reached = False
        for n, variant in enumerate(query_variants(route, world)):
            response = client_for(clients, route).get(path, variant.query)
            report.statuses[(route, n)] = response.status_code
            assert response.status_code != 429, f"throttled on {route}: the throttle patch failed"
            if not 200 <= response.status_code < 300:
                continue
            reached = True
            epic_route = "epics" in route.split("/")  # shows the epic by design, and counts it
            if epic_id and variant.leak_check and not epic_route and leaks(response, epic_id):
                report.leaks.add(route)
            try:
                found = numbers(response.json(), epic_id)
            except (ValueError, TypeError):
                continue
            report.numbers[(route, n)] = found
            if baseline is not None and not epic_route and (route, n) in baseline.numbers:
                before = baseline.numbers[(route, n)]
                changed = {k for k in before.keys() | found.keys() if before.get(k) != found.get(k)}
                if changed:
                    report.count_changes.setdefault(route, set()).update(changed)
        if not reached:
            report.not_exercised.add(route)
    return report


def unmatched(found, families):
    return {route for route in found if not any(re.search(family, route) for family in families)}


def matches_any(family, found):
    return any(re.search(family, route) for route in found)


def dump(report, path):
    """Write a report for reading by hand while filling the tables."""
    with open(path, "w") as out:
        json.dump(
            {
                "leaks": sorted(report.leaks),
                "not_exercised": sorted(report.not_exercised),
                "count_changes": {k: sorted(v) for k, v in sorted(report.count_changes.items())},
                "statuses": {f"{r} [{n}]": s for (r, n), s in sorted(report.statuses.items())},
            },
            out,
            indent=1,
        )
