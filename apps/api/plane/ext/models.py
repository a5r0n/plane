# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Fork tables (label squadron_ext); see FORK.md, Migrations."""

from django.conf import settings
from django.db import models

from plane.db.models import ProjectBaseModel


class WorkItemStep(ProjectBaseModel):
    """One step in a work item's path; the current step is the first pending or failed one."""

    class Status(models.TextChoices):
        PENDING = "pending"
        DONE = "done"
        FAILED = "failed"
        SKIPPED = "skipped"

    # statuses that hold the path at this step
    OPEN = (Status.PENDING, Status.FAILED)

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="squadron_steps")
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="squadron_steps"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    note = models.TextField(blank=True, default="")
    sort_order = models.FloatField(default=0)
    not_before = models.DateTimeField(null=True, blank=True)

    ORDER = ("sort_order", "created_at", "id")

    class Meta:
        db_table = "squadron_ext_work_item_steps"
        ordering = ("sort_order", "created_at", "id")
        indexes = [models.Index(fields=["issue", "sort_order"], name="squadron_ext_step_issue_order")]


class CustomProperty(ProjectBaseModel):
    """A typed property defined on a project; values live in CustomValue (see FORK.md, Custom properties)."""

    class Type(models.TextChoices):
        TEXT = "text"
        NUMBER = "number"
        BOOLEAN = "boolean"
        DATE = "date"
        DATETIME = "datetime"
        CHOICE = "choice"
        MEMBER = "member"
        URL = "url"

    ROLES = ((20, "Admin"), (15, "Member"), (5, "Guest"))

    name = models.CharField(max_length=255)
    key = models.CharField(max_length=64)
    type = models.CharField(max_length=16, choices=Type.choices)
    description = models.TextField(blank=True, default="")
    options = models.JSONField(default=list, blank=True)
    multiple = models.BooleanField(default=False)
    visible = models.BooleanField(default=True)
    write_role = models.PositiveSmallIntegerField(choices=ROLES, default=15)
    sort_order = models.FloatField(default=65535)

    class Meta:
        db_table = "squadron_ext_custom_properties"
        ordering = ("sort_order", "created_at")
        # no deleted_at condition: a deleted property's key stays reserved
        constraints = [models.UniqueConstraint(fields=["project", "key"], name="squadron_ext_property_project_key")]


class CustomValue(ProjectBaseModel):
    """One value of a property on a work item; a multi-value property has one row per value."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="squadron_values")
    property = models.ForeignKey(CustomProperty, on_delete=models.CASCADE, related_name="values")
    value_text = models.TextField(null=True, blank=True)
    value_number = models.DecimalField(max_digits=30, decimal_places=10, null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    position = models.PositiveSmallIntegerField(default=0)  # order within a multi-value list

    class Meta:
        db_table = "squadron_ext_custom_values"
        ordering = ("position",)
        indexes = [models.Index(fields=["property", "issue"], name="squadron_ext_value_prop_issue")]
