# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Per-request epic scope for Issue.issue_objects; imports no models (db.models imports this)."""

from contextlib import contextmanager
from contextvars import ContextVar

MODES = ("exclude", "only", "all")
_mode = ContextVar("squadron_epic_scope", default="all")
_cache = ContextVar("squadron_epic_scope_cache", default=None)


def apply_epic_scope(queryset):
    mode = _mode.get()
    if mode == "exclude":
        return queryset.exclude(type__is_epic=True)
    if mode == "only":
        return queryset.filter(type__is_epic=True)
    return queryset


def current_scope():
    return _mode.get()


def scope_cache():
    """A dict that lives as long as the innermost epic_scope; empty outside one."""
    return _cache.get() if _cache.get() is not None else {}


@contextmanager
def epic_scope(mode):
    if mode not in MODES:
        raise ValueError(f"unknown epic scope {mode!r}")
    token, cache_token = _mode.set(mode), _cache.set({})
    try:
        yield
    finally:
        _cache.reset(cache_token)
        _mode.reset(token)
