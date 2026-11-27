# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Webhook settings, read from the environment on each use."""

import os
import uuid


def secret():
    """The webhook secret; empty means the endpoint is off."""
    return os.environ.get("GITHUB_WEBHOOK_SECRET", "")


def repos():
    """{"owner/repo" (lowercase): project id} from GITHUB_WEBHOOK_REPOS="owner/repo=<project id>,..."."""
    found = {}
    for entry in os.environ.get("GITHUB_WEBHOOK_REPOS", "").split(","):
        name, _, project = entry.strip().partition("=")
        try:
            found[name.strip().lower()] = str(uuid.UUID(project.strip()))
        except ValueError:
            continue
    return found


def actor():
    """The user the rows are written as, or None."""
    value = os.environ.get("GITHUB_WEBHOOK_ACTOR", "").strip()
    try:
        return str(uuid.UUID(value)) if value else None
    except ValueError:
        return None


def client_agent():
    return os.environ.get("GITHUB_WEBHOOK_CLIENT_AGENT", "").strip()[:255] or "github"
