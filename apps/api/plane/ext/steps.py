# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Work item steps on the v1 API: CRUD, set-path, reorder, and steps in an item read. See FORK.md, Steps."""

import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response

from plane.api.views.base import BaseAPIView
from plane.api.views.issue import IssueDetailAPIEndpoint, WorkspaceIssueAPIEndpoint
from plane.app.permissions import ProjectEntityPermission
from plane.bgtasks.webhook_task import webhook_activity
from plane.db.models import Issue, IssueActivity, WorkspaceMember
from plane.ext.models import WorkItemStep
from plane.utils.host import base_host

STEP_FIELDS = ("steps", "current_step")
GAP = 1000.0  # sort_order spacing


class StepSerializer(serializers.ModelSerializer):
    actor = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = WorkItemStep
        fields = (
            "id",
            "issue",
            "title",
            "detail",
            "actor",
            "status",
            "note",
            "sort_order",
            "not_before",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )
        read_only_fields = ("id", "issue", "sort_order", "created_at", "updated_at", "created_by", "updated_by")


class StepInputSerializer(serializers.ModelSerializer):
    """What a caller may write; the actor must be an active member of the item's workspace."""

    actor = serializers.UUIDField(allow_null=True, required=False)

    class Meta:
        model = WorkItemStep
        fields = ("title", "detail", "actor", "status", "note", "not_before")

    def validate_actor(self, value):
        if value is None:
            return None
        workspace_id = self.context["workspace_id"]
        if not WorkspaceMember.objects.filter(workspace_id=workspace_id, member_id=value, is_active=True).exists():
            raise serializers.ValidationError("actor must be an active member of the workspace")
        return value


def ordered(issue_id):
    return WorkItemStep.objects.filter(issue_id=issue_id).order_by(*WorkItemStep.ORDER)


def plain(data):
    """Serializer output as JSON-native values, for activity rows and celery."""
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def step_data(step):
    return plain(StepSerializer(step).data)


def path_data(issue_id):
    return plain(StepSerializer(ordered(issue_id), many=True).data)


def same_path(old, new):
    """False when the path's steps, order or content changed; save() alone moves updated_at."""
    stamp = ("updated_at", "updated_by", "sort_order")

    def strip(steps):
        return [{key: value for key, value in step.items() if key not in stamp} for step in steps]

    return strip(old) == strip(new)


def current_of(steps):
    """The first pending or failed step: a failed step holds the path until it's retried or skipped."""
    return next((step for step in steps if step["status"] in WorkItemStep.OPEN), None)


def steps_for(issue_ids):
    """issue id -> {"steps": [...], "current_step": step or None}."""
    by_issue = {str(issue_id): [] for issue_id in issue_ids}
    rows = WorkItemStep.objects.filter(issue_id__in=list(issue_ids)).order_by("issue_id", *WorkItemStep.ORDER)
    for row in plain(StepSerializer(rows, many=True).data):
        by_issue[str(row["issue"])].append(row)
    return {key: {"steps": steps, "current_step": current_of(steps)} for key, steps in by_issue.items()}


def apply_fields(step, data):
    for field, value in data.items():
        if field == "actor":
            step.actor_id = value
        else:
            setattr(step, field, value)


def renumber(steps):
    for index, step in enumerate(steps):
        step.sort_order = (index + 1) * GAP
    WorkItemStep.objects.bulk_update(steps, ["sort_order"])


def record(request, issue, verb, comment, old_value, new_value, step_id=None):
    """One activity row and an updated_at bump in this transaction; the issue webhook after commit."""
    now = timezone.now()
    IssueActivity.objects.create(
        issue_id=issue.id,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        actor_id=request.user.id,
        verb=verb,
        field="step",
        old_value=None if old_value is None else json.dumps(old_value),
        new_value=None if new_value is None else json.dumps(new_value),
        comment=comment,
        old_identifier=step_id if verb != "created" else None,
        new_identifier=step_id if verb != "deleted" else None,
        epoch=int(now.timestamp()),
    )
    # a queryset update: never touches state, assignees or anything else on the item
    Issue.all_objects.filter(pk=issue.id).update(updated_at=now)
    slug, origin = request.parser_context["kwargs"]["slug"], base_host(request=request, is_app=True)
    transaction.on_commit(
        lambda: webhook_activity.delay(
            event="issue",
            verb="updated",
            field="step",
            old_value=old_value,
            new_value=new_value,
            actor_id=str(request.user.id),
            slug=slug,
            current_site=origin,
            event_id=str(issue.id),
            old_identifier=step_id if verb != "created" else None,
            new_identifier=step_id if verb != "deleted" else None,
        )
    )


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=code)


class StepBase(BaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def get_issue(self, slug, project_id, issue_id, lock=False):
        queryset = Issue.objects.filter(pk=issue_id, project_id=project_id, workspace__slug=slug)
        if lock:  # one step write at a time per item, so orders and activity rows don't interleave
            queryset = queryset.select_for_update(of=("self",))  # not the joined workspace row
        return queryset.first()

    def input(self, issue, data, partial=False):
        serializer = StepInputSerializer(data=data, partial=partial, context={"workspace_id": issue.workspace_id})
        serializer.is_valid(raise_exception=True)
        return dict(serializer.validated_data)


class StepListCreateEndpoint(StepBase):
    def get(self, request, slug, project_id, issue_id):
        if self.get_issue(slug, project_id, issue_id) is None:
            return _error("Work item not found", status.HTTP_404_NOT_FOUND)
        return Response(path_data(issue_id))

    @transaction.atomic
    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id, lock=True)
        if issue is None:
            return _error("Work item not found", status.HTTP_404_NOT_FOUND)
        data = self.input(issue, request.data)
        steps = list(ordered(issue_id))
        position = request.data.get("position", len(steps))
        if isinstance(position, bool) or not isinstance(position, int) or not 0 <= position <= len(steps):
            return _error(f"position must be a whole number from 0 to {len(steps)}")
        step = WorkItemStep(issue=issue, project_id=issue.project_id, workspace_id=issue.workspace_id)
        apply_fields(step, data)
        step.save()
        steps.insert(position, step)
        renumber(steps)
        step.refresh_from_db()
        new = step_data(step)
        record(request, issue, "created", f"added step {step.title!r}", None, new, step_id=str(step.id))
        return Response(new, status=status.HTTP_201_CREATED)


class StepDetailEndpoint(StepBase):
    def get_step(self, issue_id, step_id):
        return WorkItemStep.objects.filter(pk=step_id, issue_id=issue_id).first()

    def get(self, request, slug, project_id, issue_id, step_id):
        step = self.get_issue(slug, project_id, issue_id) and self.get_step(issue_id, step_id)
        if not step:
            return _error("Step not found", status.HTTP_404_NOT_FOUND)
        return Response(step_data(step))

    @transaction.atomic
    def patch(self, request, slug, project_id, issue_id, step_id):
        issue = self.get_issue(slug, project_id, issue_id, lock=True)
        step = issue and self.get_step(issue_id, step_id)
        if not step:
            return _error("Step not found", status.HTTP_404_NOT_FOUND)
        data = self.input(issue, request.data, partial=True)
        old = step_data(step)
        apply_fields(step, data)
        step.save()
        new = step_data(step)
        changed = [key for key in StepInputSerializer.Meta.fields if old.get(key) != new.get(key)]
        if changed:
            comment = f"updated step {step.title!r}: {', '.join(changed)}"
            record(request, issue, "updated", comment, old, new, step_id=str(step.id))
        return Response(new)

    @transaction.atomic
    def delete(self, request, slug, project_id, issue_id, step_id):
        issue = self.get_issue(slug, project_id, issue_id, lock=True)
        step = issue and self.get_step(issue_id, step_id)
        if not step:
            return _error("Step not found", status.HTTP_404_NOT_FOUND)
        old = step_data(step)
        step.delete(soft=False)  # history lives in the activity row
        record(request, issue, "deleted", f"removed step {step.title!r}", old, None, step_id=old["id"])
        return Response(status=status.HTTP_204_NO_CONTENT)


def _step_ids(values, name):
    if not isinstance(values, list):
        raise ValueError(f"{name} must be a list")
    out = []
    for value in values:
        try:
            out.append(str(uuid.UUID(str(value))))
        except ValueError:
            raise ValueError(f"{value!r} in {name} is not a step id") from None
    if len(set(out)) != len(out):
        raise ValueError(f"{name} names a step twice")
    return out


class StepSetPathEndpoint(StepBase):
    """POST {"steps": [...]}: the whole path in order. An entry with an id updates that step, one
    without creates a step, and steps left out are deleted."""

    @transaction.atomic
    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id, lock=True)
        if issue is None:
            return _error("Work item not found", status.HTTP_404_NOT_FOUND)
        entries = request.data.get("steps")
        if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
            return _error("steps must be a list of step objects")
        existing = {str(step.id): step for step in ordered(issue_id)}
        try:
            named = _step_ids([entry["id"] for entry in entries if entry.get("id") is not None], "steps")
        except ValueError as exc:
            return _error(str(exc))
        unknown = [step_id for step_id in named if step_id not in existing]
        if unknown:
            return _error(f"not steps of this work item: {', '.join(unknown)}")

        # validate every entry before writing any
        plans = []
        for index, entry in enumerate(entries):
            fields = {key: value for key, value in entry.items() if key != "id"}
            serializer = StepInputSerializer(
                data=fields, partial=entry.get("id") is not None, context={"workspace_id": issue.workspace_id}
            )
            if not serializer.is_valid():
                return Response({"steps": {str(index): serializer.errors}}, status=status.HTTP_400_BAD_REQUEST)
            plans.append((entry.get("id"), dict(serializer.validated_data)))

        old = path_data(issue_id)
        steps = []
        for step_id, data in plans:
            step = (
                existing[str(uuid.UUID(str(step_id)))]
                if step_id
                else WorkItemStep(issue=issue, project_id=issue.project_id, workspace_id=issue.workspace_id)
            )
            apply_fields(step, data)
            step.save()
            steps.append(step)
        kept = {str(step.id) for step in steps}
        for step_id, step in existing.items():
            if step_id not in kept:
                step.delete(soft=False)  # history lives in the activity row
        renumber(steps)
        new = path_data(issue_id)
        if not same_path(old, new):
            record(request, issue, "updated", f"set the path ({len(new)} steps)", old, new)
        return Response(new)


class StepReorderEndpoint(StepBase):
    """POST {"step_ids": [...]}: every step of the item, in the new order."""

    @transaction.atomic
    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id, lock=True)
        if issue is None:
            return _error("Work item not found", status.HTTP_404_NOT_FOUND)
        try:
            step_ids = _step_ids(request.data.get("step_ids"), "step_ids")
        except ValueError as exc:
            return _error(str(exc))
        existing = {str(step.id): step for step in ordered(issue_id)}
        if set(step_ids) != set(existing):
            return _error("step_ids must name every step of this work item exactly once")
        old = path_data(issue_id)
        renumber([existing[step_id] for step_id in step_ids])
        new = path_data(issue_id)
        if [s["id"] for s in old] != [s["id"] for s in new]:
            record(request, issue, "updated", "reordered the path", old, new)
        return Response(new)


class StepFieldsMixin:
    """An item read with fields=steps,current_step: those keys are ours, the rest go to upstream."""

    def get(self, request, *args, **kwargs):
        asked = [field for field in request.GET.get("fields", "").split(",") if field]
        wanted = [field for field in asked if field in STEP_FIELDS]
        if not wanted:
            return super().get(request, *args, **kwargs)
        rest = [field for field in asked if field not in STEP_FIELDS]
        query = request._request.GET.copy()
        query["fields"] = ",".join(rest or ["id"])
        if "id" not in rest:
            query["fields"] += ",id" if rest else ""
        request._request.GET = query
        response = super().get(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK and isinstance(response.data, dict):
            found = steps_for([response.data["id"]])[str(response.data["id"])]
            for field in wanted:
                response.data[field] = found[field]
            if "id" not in rest and rest:
                response.data.pop("id", None)
        return response


class WorkItemDetailAPIEndpoint(StepFieldsMixin, IssueDetailAPIEndpoint):
    pass


class WorkItemByIdentifierAPIEndpoint(StepFieldsMixin, WorkspaceIssueAPIEndpoint):
    pass
