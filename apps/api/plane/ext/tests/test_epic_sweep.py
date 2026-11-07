# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re

import pytest
from rest_framework.test import APIClient

from plane.ext.epics import routes
from plane.ext.tests.helpers import ids, row_ids
from plane.ext.tests.sweep import get_route, matches_any, sweep, unmatched

pytestmark = pytest.mark.django_db
P, W = routes.P, routes.W


def test_sweep(world, clients, monkeypatch):
    sweep(world, clients)  # warm-up: GET handlers create rows lazily
    baseline = sweep(world, clients)
    world.add_epic()
    report = sweep(world, clients, baseline=baseline)

    assert report.leaks - routes.SHOWS.keys() == set()
    assert unmatched(report.not_exercised, routes.UNEXERCISED) == set()
    assert report.count_changes.keys() - routes.COUNTS.keys() - routes.SHOWS.keys() == set()

    # Tables have no stale entries, and no excuse covers a named route.
    assert routes.HIDE <= report.walked
    assert routes.COUNTS.keys() <= report.count_changes.keys()
    assert all(matches_any(family, report.not_exercised) for family in routes.UNEXERCISED)
    assert not {route for route in routes.HIDE if matches_any_family(route)}
    assert not routes.HIDE & report.not_exercised

    # Control: unhidden, every named route shows the epic, so none passes for the wrong reason.
    monkeypatch.setattr(routes, "HIDE", frozenset())
    control = sweep(world, clients, baseline=baseline)
    assert routes.LISTS - control.leaks == set()
    assert routes.TOTALS - control.count_changes.keys() == set()


def matches_any_family(route):
    return any(re.search(family, route) for family in routes.UNEXERCISED)


@pytest.mark.parametrize(
    "route,query",
    [
        (P + "search-issues/", {"search": "Sweep epic"}),
        (W + "search/", {"search": "Sweep epic"}),
        ("v1/" + W + "work-items/search/", {"search": "Sweep epic"}),
    ],
)
def test_lazy_lists_stay_hidden_after_rendering(clients, world, route, query):
    """Django renders after the view returns: a lazy queryset would escape the scope."""
    world.add_epic()
    assert world.epic_id not in row_ids(get_route(clients, world, route, query))


def test_search_issues_shows_epics_only_with_issue_id(session_client, url, epic, normal):
    assert str(epic.id) not in ids(session_client.get(url("search-issues/"), {"search": epic.name}))
    r = session_client.get(url("search-issues/"), {"search": epic.name, "parent": "true", "issue_id": str(normal.id)})
    assert r.status_code == 200 and str(epic.id) in ids(r)


def test_issue_id_exempts_nothing_else(session_client, url, epic, normal):
    assert str(epic.id) not in ids(session_client.get(url("issues/"), {"issue_id": str(normal.id)}))


def test_an_anonymous_board_hides_epics(world):
    world.add_epic()
    r = APIClient().get(f"/api/public/anchor/{world.anchor}/issues/")
    assert r.status_code == 200
    assert world.epic_id not in row_ids(r.json())


def test_post_to_a_hidden_route_can_use_an_epic_parent(session_client, url, epic):
    r = session_client.post(url("issues/"), {"name": "c", "parent": str(epic.id)}, format="json")
    assert r.status_code == 201, r.content
