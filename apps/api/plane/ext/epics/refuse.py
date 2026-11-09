# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Refuse to put an epic in a cycle or module: an epic spans cycles, and their lists hide it."""

import uuid

from rest_framework import status
from rest_framework.exceptions import APIException

from plane.db.models import Issue


class EpicRefused(APIException):
    status_code = status.HTTP_400_BAD_REQUEST


def _as_list(data, key):
    if hasattr(data, "getlist"):  # a form body
        return data.getlist(key)
    value = data.get(key) if isinstance(data, dict) else None
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def sent_ids(request, kwargs):
    """The item ids a POST would add: the url's item when it sends modules, else the body's `issues`."""
    if "issue_id" in kwargs:
        return [kwargs["issue_id"]] if _as_list(request.data, "modules") else []
    return _as_list(request.data, "issues")


def epics_among(ids):
    parsed = set()
    for value in ids:
        try:
            parsed.add(uuid.UUID(str(value)))
        except ValueError:
            continue  # upstream answers bad ids its own way
    if not parsed:
        return []
    return sorted(str(pk) for pk in Issue.objects.filter(pk__in=parsed, type__is_epic=True).values_list("pk", flat=True))


class RefuseEpicsMixin:
    """Checks after auth and permission classes, before the handler writes anything."""

    refuse_target = "cycle"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method != "POST":
            return
        epics = epics_among(sent_ids(request, kwargs))
        if epics:
            raise EpicRefused({"error": f"An epic can't be added to a {self.refuse_target}.", "ids": epics})


def refusing(callback, target):
    """The same route's view, rebuilt on a subclass that refuses epics."""
    cls = type(f"RefuseEpics{callback.cls.__name__}", (RefuseEpicsMixin, callback.cls), {"refuse_target": target})
    actions = getattr(callback, "actions", None)
    if actions:
        return cls.as_view(actions, **callback.initkwargs)
    return cls.as_view(**callback.initkwargs)
