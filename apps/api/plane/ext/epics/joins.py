# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""In exclude scope, joins through cycle, module and project links skip epics.

Upstream counts cycle, module and project totals by aggregating over these joins, which the
issue manager never sees. Django adds get_extra_restriction() to a join's ON clause, so an epic,
or its cycle or module link row, joins as nothing and drops out of every such count.
"""

from django.db.models.lookups import In, IsNull
from django.db.models.sql.where import OR, WhereNode

from plane.db.models import CycleIssue, Issue, IssueType, ModuleIssue
from plane.ext.epics.scope import current_scope, scope_cache


def epic_type_ids():
    cache = scope_cache()
    if "epic_types" not in cache:
        cache["epic_types"] = list(IssueType.objects.filter(is_epic=True).values_list("id", flat=True))
    return cache["epic_types"]


def not_epic(issue_alias):
    """`type_id IS NULL OR type_id NOT IN (epic types)` on the issue table, in exclude scope only."""
    if issue_alias is None or current_scope() != "exclude":
        return None  # None: subquery pushdown, which names no issue alias
    ids = epic_type_ids()
    if not ids:
        return None
    col = Issue._meta.get_field("type").get_col(issue_alias)
    return WhereNode([IsNull(col, True), WhereNode([In(col, ids)], negated=True)], connector=OR)


def not_epic_link(link, link_alias):
    """On a cycle or module link row: `issue_id NOT IN (epics)`, so a count of issue ids skips it."""
    if link_alias is None or current_scope() != "exclude" or not epic_type_ids():
        return None
    epics = Issue.objects.filter(type_id__in=epic_type_ids()).values("pk").query
    return WhereNode([In(link._meta.get_field("issue").get_col(link_alias), epics)], negated=True)


def install():
    # For a foreign key, Django passes the alias of the table it points at first, in both directions.
    for link, owner in ((CycleIssue, "cycle"), (ModuleIssue, "module")):
        link._meta.get_field("issue").get_extra_restriction = lambda alias, related_alias: not_epic(alias)
        link._meta.get_field(owner).get_extra_restriction = lambda alias, related_alias, link=link: (
            not_epic_link(link, related_alias) if alias is not None else None
        )
    Issue._meta.get_field("project").get_extra_restriction = lambda alias, related_alias: (
        not_epic(related_alias) if alias is not None else None
    )
