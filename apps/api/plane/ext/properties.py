# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Custom properties: definitions, typed values and `custom_fields` on v1 work items (FORK.md)."""

import uuid
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from plane.db.models import ProjectMember
from plane.ext.models import CustomProperty

T = CustomProperty.Type
KEY_RE = r"^[a-z][a-z0-9_]{0,63}$"
MAX_TEXT = 255
MAX_URL = 2048

# the CustomValue column each type is stored in
COLUMN = {
    T.TEXT: "value_text",
    T.URL: "value_text",
    T.CHOICE: "value_text",
    T.NUMBER: "value_number",
    T.BOOLEAN: "value_bool",
    T.DATE: "value_date",
    T.DATETIME: "value_datetime",
    T.MEMBER: "value_member_id",
}


def _text(prop, raw):
    if not isinstance(raw, str) or "\n" in raw or "\r" in raw or len(raw) > MAX_TEXT:
        raise ValueError(f"a single line of text up to {MAX_TEXT} characters")
    return raw


def _number(prop, raw):
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ValueError("a number")
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise ValueError("a number") from None
    if not value.is_finite() or abs(value) >= Decimal(10) ** 20:
        raise ValueError("a finite number below 1e20")
    return value


def _boolean(prop, raw):
    if not isinstance(raw, bool):
        raise ValueError("true or false")
    return raw


def _date(prop, raw):
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise ValueError("a date, YYYY-MM-DD") from None


def _datetime(prop, raw):
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00") if isinstance(raw, str) else raw)
    except (TypeError, ValueError):
        value = None
    if value is None or value.tzinfo is None:
        raise ValueError("an ISO 8601 timestamp with a time zone")
    return value.astimezone(dt_timezone.utc)


def _choice(prop, raw):
    if raw not in {option["id"] for option in prop.options}:
        raise ValueError(f"one of the option ids: {', '.join(option['id'] for option in prop.options)}")
    return raw


def _member(prop, raw):
    try:
        member_id = uuid.UUID(str(raw))
    except ValueError:
        raise ValueError("a project member's user id") from None
    if not ProjectMember.objects.filter(project_id=prop.project_id, member_id=member_id, is_active=True).exists():
        raise ValueError("a project member's user id")
    return member_id


def _url(prop, raw):
    parsed = urlparse(raw) if isinstance(raw, str) else None
    if not parsed or parsed.scheme not in ("http", "https") or not parsed.netloc or len(raw) > MAX_URL:
        raise ValueError("an http or https URL")
    return raw


COERCE = {
    T.TEXT: _text,
    T.NUMBER: _number,
    T.BOOLEAN: _boolean,
    T.DATE: _date,
    T.DATETIME: _datetime,
    T.CHOICE: _choice,
    T.MEMBER: _member,
    T.URL: _url,
}


def coerce(prop, raw, held=()):
    """JSON input -> the list of column values to store ([] clears); ValueError says what's expected.

    A value in `held` (already on the item) skips the per-value check, so a disabled option or a
    member who left survives a resend."""
    if raw is None:
        return []
    if prop.multiple:
        if not isinstance(raw, list):
            raise ValueError("a list of values")
        items = raw
    elif isinstance(raw, list):
        raise ValueError("a single value, not a list")
    else:
        items = [raw]
    values = []
    for item in items:
        value = item if _key(prop, item) in held else COERCE[prop.type](prop, item)
        if value not in values:
            values.append(value)
    return values


def _key(prop, item):
    """The form a raw input takes when compared with stored values (held)."""
    return str(item) if prop.type == T.MEMBER else item


def stored(prop, value):
    """A CustomValue's column value for prop."""
    return getattr(value, COLUMN[prop.type])


def as_json(prop, value):
    if prop.type == T.NUMBER:
        return int(value) if value == value.to_integral_value() else float(value)
    if prop.type == T.DATETIME:
        return value.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")
    if prop.type in (T.DATE, T.MEMBER):
        return str(value) if prop.type == T.MEMBER else value.isoformat()
    return value


def present(prop, values):
    """Stored rows -> the JSON a work item's custom_fields shows for prop."""
    items = [as_json(prop, stored(prop, value)) for value in values]
    if prop.multiple:
        return items
    return items[0] if items else None
