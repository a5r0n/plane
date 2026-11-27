# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Workspace activity feed: what changed across the workspace, per reader, with an optional long-poll."""

import hashlib
import secrets
import time
import uuid
from datetime import timedelta, timezone as dt_timezone

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers, status
from rest_framework.response import Response

from plane.api.views.base import BaseAPIView
from plane.db.models import IssueActivity
from plane.ext.activity import HIDDEN_FIELDS, ActivitySerializer

WINDOW = timedelta(minutes=10)
READER_TTL = 600  # seconds; refreshed on every call
MAX_WAIT = 25
MAX_PER_PAGE = 100
POLL_INTERVAL = 1.0


class FeedSerializer(ActivitySerializer):
    issue_identifier = serializers.SerializerMethodField()

    def get_issue_identifier(self, activity):
        if not activity.issue_id:
            return None
        return f"{activity.project.identifier}-{activity.issue.sequence_id}"


class FeedError(Exception):
    def __init__(self, code, message, http_status=status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, http_status

    def response(self):
        return Response({"code": self.code, "error": self.message}, status=self.http_status)


def csv(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def bounded_int(params, name, default, low, high):
    raw = params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or not low <= value <= high:
        raise FeedError("INVALID_PARAM", f"{name} must be a whole number from {low} to {high}.")
    return value


def parse_since(raw):
    # a '+' offset arrives as a space when the client didn't encode it
    try:
        since = parse_datetime(raw.replace(" ", "+")) if raw else None
    except ValueError:
        since = None
    if since is None:
        raise FeedError("INVALID_PARAM", "since must be an ISO 8601 datetime.")
    return since if since.tzinfo else since.replace(tzinfo=dt_timezone.utc)


def row_key(row_id, created_at):
    """A row is delivered once per created_at, so a re-dated row goes out again."""
    return f"{row_id}:{created_at.isoformat()}"


def reader_key(reader):
    return f"squadron:feed:reader:{reader}"


def token_hash(request):
    return hashlib.sha256(str(request.auth).encode()).hexdigest()


class WorkspaceActivityFeedEndpoint(BaseAPIView):
    def rows(self, request, slug):
        params = request.query_params
        rows = IssueActivity.objects.filter(
            ~Q(field__in=HIDDEN_FIELDS),
            workspace__slug=slug,
            project__project_projectmember__member=request.user,
            project__project_projectmember__is_active=True,
            project__project_projectmember__deleted_at__isnull=True,
            project__archived_at__isnull=True,
        ).distinct()
        if projects := csv(params.get("project")):
            try:
                projects = [uuid.UUID(project) for project in projects]
            except ValueError:
                raise FeedError("INVALID_PARAM", "project must be a comma list of project ids.")
            rows = rows.filter(project_id__in=projects)
        if fields := csv(params.get("field")):
            rows = rows.filter(field__in=fields)
        if excluded := csv(params.get("exclude_field")):
            rows = rows.exclude(field__in=excluded)
        if agents := csv(params.get("agent")):
            rows = rows.filter(squadron_provenance__client_agent__in=agents)
        return rows

    def serialize(self, ids):
        rows = (
            IssueActivity.objects.filter(id__in=ids)
            .select_related("actor", "workspace", "issue", "project", "squadron_provenance__api_token")
            .order_by("created_at", "id")
        )
        return FeedSerializer(rows, many=True, fields=self.fields, expand=self.expand).data

    def get(self, request, slug):
        try:
            return self.feed(request, slug)
        except FeedError as error:
            return error.response()

    def feed(self, request, slug):
        params = request.query_params
        # Postgres can't store or compare a NUL byte
        if any("\x00" in value for _, values in params.lists() for value in values):
            raise FeedError("INVALID_PARAM", "Parameters can't contain a NUL byte.")
        wait = bounded_int(params, "wait", 0, 0, MAX_WAIT)
        per_page = bounded_int(params, "per_page", MAX_PER_PAGE, 1, MAX_PER_PAGE)
        reader = params.get("reader")
        since = params.get("since")
        if reader and since:
            raise FeedError("INVALID_PARAM", "since works only without reader.")
        if not reader and not since:
            raise FeedError("INVALID_PARAM", "Send reader (or reader=new), or since.")
        rows = self.rows(request, slug)
        if reader:
            return self.read_as_reader(request, rows, reader, wait, per_page)
        return self.read_since(rows, parse_since(since), wait, per_page)

    def hold(self, wait, poll):
        """Run poll() until it returns rows or the wait runs out."""
        deadline = time.monotonic() + wait
        while True:
            found = poll()
            left = deadline - time.monotonic()
            if found or left <= 0:
                return found
            time.sleep(min(POLL_INTERVAL, left))

    def read_since(self, rows, since, wait, per_page):
        def poll():
            ordered = rows.filter(created_at__gte=since).order_by("created_at", "id")
            return list(ordered.values_list("id", flat=True)[: per_page + 1])

        ids = self.hold(wait, poll)
        return Response({"more": len(ids) > per_page, "results": self.serialize(ids[:per_page])})

    def load_reader(self, request, reader):
        if reader == "new":
            token = secrets.token_urlsafe(24)
            return token, {"token": token_hash(request), "user": str(request.user.id), "acked": {}, "batch": None}
        record = cache.get(reader_key(reader))
        if record is None:
            raise FeedError("READER_GONE", "Unknown or expired reader; start a new one.", status.HTTP_410_GONE)
        if record["token"] != token_hash(request) or record["user"] != str(request.user.id):
            raise FeedError("READER_FORBIDDEN", "This reader belongs to another API token.", status.HTTP_403_FORBIDDEN)
        return reader, record

    def read_as_reader(self, request, rows, reader, wait, per_page):
        reader, record = self.load_reader(request, reader)
        ack = request.query_params.get("ack")
        batch = record.get("batch")
        if ack and batch and ack == batch["id"]:
            record["acked"].update(batch["keys"])
            record["batch"] = None
        call = record["call"] = secrets.token_urlsafe(8)
        cache.set(reader_key(reader), record, READER_TTL)

        def poll():
            start = timezone.now() - WINDOW
            undelivered = [
                (row_id, created_at)
                for row_id, created_at in rows.filter(created_at__gte=start)
                .order_by("created_at", "id")
                .values_list("id", "created_at")
                if row_key(row_id, created_at) not in record["acked"]
            ]
            return undelivered[: per_page + 1]

        pending = self.hold(wait, poll)
        # a newer call on this reader took over while we held: its state wins
        latest = cache.get(reader_key(reader))
        if latest is None or latest.get("call") != call:
            return Response({"reader": reader, "batch": None, "more": False, "results": []})
        page = pending[:per_page]

        # forget acks for rows that have left the window
        cutoff = (timezone.now() - WINDOW).timestamp()
        record["acked"] = {key: at for key, at in record["acked"].items() if at >= cutoff}
        if page:
            batch = {
                "id": secrets.token_urlsafe(16),
                "keys": {row_key(row_id, created_at): created_at.timestamp() for row_id, created_at in page},
            }
        else:
            batch = None
        record["batch"] = batch
        cache.set(reader_key(reader), record, READER_TTL)
        return Response(
            {
                "reader": reader,
                "batch": batch["id"] if batch else None,
                "more": len(pending) > per_page,
                "results": self.serialize([row_id for row_id, _ in page]),
            }
        )
