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
