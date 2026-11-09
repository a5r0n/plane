# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Epic route tables: data only. Patterns are full, relative to api/."""

W = "workspaces/<str:slug>/"
P = W + "projects/<uuid:project_id>/"
ISSUE = P + "issues/<uuid:issue_id>/"
EPIC = P + "epics/<uuid:issue_id>/"
ASSETS = "assets/v2/" + P

# upstream session route -> its epic twin; each runs in scope "all"
ALIASES = {
    P + "issues/list/": P + "epics/list/",
    P + "issues/<uuid:pk>/": P + "epics/<uuid:pk>/",
    P + "issues/<uuid:pk>/archive/": P + "epics/<uuid:pk>/archive/",
    P + "user-properties/": P + "epics-user-properties/",
    P + "work-items/<uuid:work_item_id>/description-versions/": P + "epics/<uuid:work_item_id>/description-versions/",
    P + "work-items/<uuid:work_item_id>/description-versions/<uuid:pk>/": (
        P + "epics/<uuid:work_item_id>/description-versions/<uuid:pk>/"
    ),
    ASSETS + "issues/<uuid:issue_id>/attachments/": ASSETS + "epics/<uuid:issue_id>/attachments/",
    ASSETS + "issues/<uuid:issue_id>/attachments/<uuid:pk>/": ASSETS + "epics/<uuid:issue_id>/attachments/<uuid:pk>/",
}

SUB_RENAMES = {"sub-issues/": "issues/", "issue-links/": "links/"}

# tails under issues/<uuid:issue_id>/ that epics reuse, renamed where SUB_RENAMES says
ISSUE_TAILS = [
    "sub-issues/",
    "issue-links/",
    "issue-links/<uuid:pk>/",
    "issue-attachments/",
    "issue-attachments/<uuid:pk>/",
    "history/",
    "comments/",
    "comments/<uuid:pk>/",
    "issue-subscribers/",
    "issue-subscribers/<uuid:subscriber_id>/",
    "subscribe/",
    "reactions/",
    "reactions/<str:reaction_code>/",
    "issue-relation/",
    "remove-relation/",
    "versions/",
    "versions/<uuid:pk>/",
    "meta/",
]


def _rename(tail):
    for old, new in SUB_RENAMES.items():
        if tail.startswith(old):
            return new + tail[len(old) :]
    return tail


ALIASES.update({ISSUE + tail: EPIC + _rename(tail) for tail in ISSUE_TAILS})

# by-id session routes that add is_epic, so the web app can pick the epic view
MARKED = [P + "issues/<uuid:pk>/", W + "work-items/<str:project_identifier>-<str:issue_identifier>/"]

# activity_type values the web app sends for an epic -> the ones the history view knows
ACTIVITY_TYPES = {"epic-property": "issue-property", "epic-comment": "issue-comment"}

# GET routes that hide epics; everything else shows them
SEARCH_ISSUES = P + "search-issues/"
V1 = "v1/"
CYCLE, MODULE = P + "cycles/<uuid:cycle_id>/", P + "modules/<uuid:module_id>/"
LISTS = {
    P + "issues/",
    P + "issues/list/",
    P + "issues-detail/",
    P + "v2/issues/",
    SEARCH_ISSUES,
    W + "search/",
    W + "issues/",
    W + "user-issues/<uuid:user_id>/",
    CYCLE + "cycle-issues/",
    MODULE + "issues/",
    V1 + P + "work-items/",
    V1 + P + "issues/",
    V1 + W + "work-items/search/",
    V1 + W + "issues/search/",
    V1 + CYCLE + "cycle-issues/",
    V1 + MODULE + "module-issues/",
    "public/anchor/<str:anchor>/issues/",
}
# POST routes that would put an epic in a cycle or module: full pattern -> which
REFUSE = {
    CYCLE + "cycle-issues/": "cycle",
    MODULE + "issues/": "module",
    ISSUE + "modules/": "module",
    V1 + CYCLE + "cycle-issues/": "cycle",
    V1 + MODULE + "module-issues/": "module",
}
# routes whose counts and analytics must not include epics
TOTALS = {
    W + "analytics/",
    W + "default-analytics/",
    W + "advance-analytics/",
    W + "advance-analytics-stats/",
    W + "advance-analytics-charts/",
    W + "saved-analytic-view/<uuid:analytic_id>/",
    P + "advance-analytics/",
    P + "advance-analytics-stats/",
    P + "advance-analytics-charts/",
    W + "project-stats/",
    W + "user-stats/<uuid:user_id>/",
    W + "user-profile/<uuid:user_id>/",
    "users/me/" + W + "dashboard/",
    W + "cycles/",
    P + "cycles/",
    P + "cycles/<uuid:pk>/",
    CYCLE + "progress/",
    CYCLE + "analytics/",
    W + "modules/",
    P + "modules/",
    P + "modules/<uuid:pk>/",
    V1 + P + "cycles/",
    V1 + P + "cycles/<uuid:pk>/",
    V1 + P + "modules/",
    V1 + P + "modules/<uuid:pk>/",
    V1 + P + "summary/",
}
HIDE = frozenset(LISTS | TOTALS)

# GET routes that show epics on purpose: full pattern -> reason
SHOWS = {
    W + "entity-search/": "the mention picker, where an epic is a valid target",
}

# GET routes whose numbers may change when an epic is added: full pattern -> reason
COUNTS = {
    W + "projects/<uuid:pk>/": "next_work_item_sequence: an epic takes a sequence id",
    W + "projects/details/": "next_work_item_sequence: an epic takes a sequence id",
}

# route families the sweep may leave unreached: regex -> reason
UNEXERCISED = {
    r"(^|/)(file-)?assets/": "files, not work items",
    r"/(comments|reactions|votes|links|issue-links|module-links|attachments|issue-attachments|versions"
    r"|description-versions|activities|steps)/<uuid:\w+>/(reactions/)?$": (
        "one row of an item's own data; the sweep has none"
    ),
    r"(intake|inbox)": "intake is off for the sweep project, and an epic never enters it",
    r"(archive/$|archived-)": "nothing is archived; archived epics have no list of their own",
    r"(members|invitations|join|api-tokens|accounts|preferences|me/profile|me/settings|themes|quick-links|stickies"
    r"|favorite|webhook|notifications|last-visited)": "people and settings, not work items",
    r"/(labels|issue-labels|states|estimates|pages|views|analytic-view|draft-issues|project-deploy-boards)"
    r"/<\w+:\w+>/": "one object of a kind the sweep doesn't make",
    r"(cycle-issues|modules/<uuid:module_id>/issues)/<uuid:issue_id>/$": "upstream answers a bare GET with 500",
    r"^(workspaces/|workspace-slug-check/|workspaces/<str:slug>/(export-issues|project-identifiers)/)$": (
        "needs a name or export format, and lists no work items"
    ),
    r"^public/workspaces/<str:slug>/project-boards/$": "upstream answers a bare GET with 500",
    r"^v1/workspaces/<str:slug>/(<drf_format_suffix:format>)?$": "no v1 GET at the workspace root",
    r"/epics/list/$": "takes the work item ids to list",
    r"^public/anchor/<str:anchor>/issues/<uuid:issue_id>/(reactions|votes)/$": "needs a signed-in board user",
}

# GET routes the sweep never calls: full pattern -> reason
SKIP = {
    "unsplash/": "calls Unsplash",
}
