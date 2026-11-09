# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Activity provenance: the request's channel, API token and client headers, carried to issue_activity."""

from celery import current_task
from crum import get_current_request

from plane.db.models import APIToken
from plane.ext.models import ActivityProvenance
from plane.utils.exception_logger import log_exception

TASK = "plane.bgtasks.issue_activities_task.issue_activity"
HEADER = "squadron_provenance"  # celery message header
SESSION_HEADER = "X-Client-Session"
AGENT_HEADER = "X-Client-Agent"
LIMIT = 255


def from_request(request):
    """The provenance dict for an authenticated request, or None."""
    if request is None:
        return None
    key = request.headers.get("X-Api-Key")
    user = getattr(request, "user", None)
    if key:
        channel, token = (
            ActivityProvenance.Channel.API,
            APIToken.objects.filter(token=key).values_list("id", flat=True).first(),
        )
    elif user is not None and user.is_authenticated:
        channel, token = ActivityProvenance.Channel.APP, None
    else:
        return None
    return {
        "channel": channel.value,
        "token": str(token) if token else None,
        "session": request.headers.get(SESSION_HEADER, "")[:LIMIT],
        "agent": request.headers.get(AGENT_HEADER, "")[:LIMIT],
    }


def stamp_provenance(sender=None, headers=None, **kwargs):
    """before_task_publish: stamp issue_activity messages with the current request's provenance."""
    if sender != TASK or headers is None:
        return
    try:
        provenance = from_request(get_current_request())
        if provenance:
            headers[HEADER] = provenance
    except Exception as e:
        log_exception(e)


def task_provenance():
    """The provenance header of the running issue_activity task, or None."""
    request = getattr(current_task, "request", None)
    if request is None:
        return None
    # a worker exposes message headers as request attributes; an eager apply(headers=) as request.headers
    return getattr(request, HEADER, None) or (getattr(request, "headers", None) or {}).get(HEADER)


def record_provenance(activities):
    """Store the running task's provenance for the activities it just created; never raises."""
    try:
        provenance = task_provenance()
        if not provenance or not activities:
            return
        token = provenance.get("token")
        if token and not APIToken.objects.filter(pk=token).exists():
            token = None  # deleted between the request and the task
        ActivityProvenance.objects.bulk_create(
            [
                ActivityProvenance(
                    activity_id=activity.id,
                    channel=provenance["channel"],
                    api_token_id=token,
                    client_session=(provenance.get("session") or "")[:LIMIT],
                    client_agent=(provenance.get("agent") or "")[:LIMIT],
                )
                for activity in activities
            ],
            ignore_conflicts=True,
        )
    except Exception as e:
        log_exception(e)
