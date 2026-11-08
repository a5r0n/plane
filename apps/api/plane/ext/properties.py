# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Custom properties: definitions, typed values and `custom_fields` on v1 work items (FORK.md)."""

import re
import uuid
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.db import transaction
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.response import Response

from plane.api.views.base import BaseAPIView
from plane.app.permissions import ProjectEntityPermission
from plane.db.models import Project, ProjectMember
from plane.ext.models import CustomProperty, CustomValue

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


# definitions


OPTION_ID_RE = r"^[a-z0-9][a-z0-9_]{0,63}$"
ADMIN = 20


def _slug(label):
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:60] or "option"


def normalize_options(raw):
    """Options input -> [{id, label, disabled}]; a missing id is derived from the label."""
    if not isinstance(raw, list):
        raise serializers.ValidationError("a list of {id?, label, disabled?}")
    given = {item.get("id") for item in raw if isinstance(item, dict)}
    options, ids = [], set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("label"), str) or not item["label"].strip():
            raise serializers.ValidationError("each option needs a non-empty label")
        if len(item["label"]) > MAX_TEXT:
            raise serializers.ValidationError(f"option labels are up to {MAX_TEXT} characters")
        option_id = item.get("id")
        if option_id is None:
            base = option_id = _slug(item["label"])
            n = 1
            while option_id in ids or option_id in given:
                n += 1
                option_id = f"{base}_{n}"
        elif not isinstance(option_id, str) or not re.match(OPTION_ID_RE, option_id):
            raise serializers.ValidationError(f"option id {option_id!r} must be lowercase letters, digits and _")
        if option_id in ids:
            raise serializers.ValidationError(f"option id {option_id!r} is repeated")
        disabled = item.get("disabled", False)
        if not isinstance(disabled, bool):
            raise serializers.ValidationError("disabled is true or false")
        ids.add(option_id)
        options.append({"id": option_id, "label": item["label"], "disabled": disabled})
    return options


class PropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomProperty
        fields = (
            "id", "name", "key", "type", "description", "options", "multiple", "visible", "write_role",
            "sort_order", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_key(self, value):
        if not re.match(KEY_RE, value):
            raise serializers.ValidationError("lowercase letters, digits and _, starting with a letter, up to 64")
        return value

    def validate_options(self, value):
        return normalize_options(value)

    def validate(self, data):
        prop_type = data.get("type", self.instance.type if self.instance else None)
        if data.get("options") and prop_type != T.CHOICE:
            raise serializers.ValidationError({"options": "only choice properties have options"})
        if data.get("multiple") and prop_type not in (T.CHOICE, T.MEMBER):
            raise serializers.ValidationError({"multiple": "only choice and member properties take several values"})
        return data


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=code)


class PropertyBase(BaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def check_admin(self, request, project_id):
        if not ProjectMember.objects.filter(
            project_id=project_id, member=request.user, role=ADMIN, is_active=True
        ).exists():
            return _error("Only project admins can change properties", status.HTTP_403_FORBIDDEN)
        return None

    def get_property(self, slug, project_id, property_id):
        return CustomProperty.objects.filter(
            pk=property_id, project_id=project_id, workspace__slug=slug
        ).first()


class PropertyListCreateEndpoint(PropertyBase):
    def get(self, request, slug, project_id):
        props = CustomProperty.objects.filter(project_id=project_id, workspace__slug=slug)
        return Response(PropertySerializer(props, many=True).data)

    @transaction.atomic
    def post(self, request, slug, project_id):
        denied = self.check_admin(request, project_id)
        if denied:
            return denied
        serializer = PropertySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data["key"]
        # all_objects: a deleted property's key stays reserved
        if CustomProperty.all_objects.filter(project_id=project_id, key=key).exists():
            return _error(f"key {key!r} is already used in this project (deleted keys stay reserved)")
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        prop = serializer.save(project=project, workspace_id=project.workspace_id)
        return Response(PropertySerializer(prop).data, status=status.HTTP_201_CREATED)


class PropertyDetailEndpoint(PropertyBase):
    def get(self, request, slug, project_id, property_id):
        prop = self.get_property(slug, project_id, property_id)
        if prop is None:
            return _error("Property not found", status.HTTP_404_NOT_FOUND)
        return Response(PropertySerializer(prop).data)

    @transaction.atomic
    def patch(self, request, slug, project_id, property_id):
        denied = self.check_admin(request, project_id)
        if denied:
            return denied
        prop = self.get_property(slug, project_id, property_id)
        if prop is None:
            return _error("Property not found", status.HTTP_404_NOT_FOUND)
        for field in ("type", "key"):
            if field in request.data and request.data[field] != getattr(prop, field):
                return _error(f"{field} can't change once a property exists")
        serializer = PropertySerializer(prop, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "options" in data:
            removed = {o["id"] for o in prop.options} - {o["id"] for o in data["options"]}
            held = (
                CustomValue.objects.filter(property=prop, value_text__in=removed).values("issue").distinct().count()
                if removed
                else 0
            )
            if held:
                return _error(
                    f"option {', '.join(sorted(removed))} is held by {held} work item"
                    f"{'s' if held != 1 else ''}; disable it instead"
                )
        if prop.multiple and data.get("multiple") is False:
            several = (
                CustomValue.objects.filter(property=prop).values("issue").annotate(n=Count("id")).filter(n__gt=1)
            )
            if several.exists():
                return _error(f"{several.count()} work items hold several values; clear them first")
        prop = serializer.save()
        return Response(PropertySerializer(prop).data)

    @transaction.atomic
    def delete(self, request, slug, project_id, property_id):
        denied = self.check_admin(request, project_id)
        if denied:
            return denied
        prop = self.get_property(slug, project_id, property_id)
        if prop is None:
            return _error("Property not found", status.HTTP_404_NOT_FOUND)
        prop.delete()  # soft: values stay stored and stop being returned
        return Response(status=status.HTTP_204_NO_CONTENT)
