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
HIDE = frozenset()
