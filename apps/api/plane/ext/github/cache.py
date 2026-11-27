# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rows waiting in Redis for their PR to be linked, and the head sha → PR map; nothing here touches the DB."""

import json
import time

from plane.settings.redis import redis_instance

TTL = 3600  # a row waits at most this long for its PR's link
RETRY = 60  # how often a waiting key is retried
HEAD_TTL = 86400
PREFIX = "squadron:github:"


def now():
    return time.time()


def _wait_key(repo, what):
    return f"{PREFIX}wait:{repo}:{what}"


def _retry_key(repo, what):
    return f"{PREFIX}retry:{repo}:{what}"


def expired(entry):
    return now() - entry["received"] >= TTL


def wait(repo, what, entry, schedule):
    """Park one entry under `what` ("pr:<n>" or "sha:<sha>"); `schedule(repo, what)` starts a retry if none is due."""
    if expired(entry):
        return
    r = redis_instance()
    key = _wait_key(repo, what)
    r.rpush(key, json.dumps(entry))
    left = int(TTL - (now() - entry["received"])) + 1
    if r.ttl(key) < left:
        r.expire(key, left)
    if r.set(_retry_key(repo, what), 1, nx=True, ex=RETRY * 3):
        schedule(repo, what)


def take(repo, what):
    """Every entry waiting under `what`, removed from Redis; the retry marker is cleared first."""
    r = redis_instance()
    r.delete(_retry_key(repo, what))
    pipe = r.pipeline()
    pipe.lrange(_wait_key(repo, what), 0, -1)
    pipe.delete(_wait_key(repo, what))
    entries, _ = pipe.execute()
    return [json.loads(e) for e in entries]


def waiting(repo, what):
    return bool(redis_instance().exists(_wait_key(repo, what)))


def remember_head(repo, sha, number):
    redis_instance().set(f"{PREFIX}head:{repo}:{sha}", number, ex=HEAD_TTL)


def head(repo, sha):
    value = redis_instance().get(f"{PREFIX}head:{repo}:{sha}")
    return int(value) if value else None
