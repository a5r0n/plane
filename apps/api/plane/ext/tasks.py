# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Celery finds the fork's tasks here."""

from plane.ext.github.tasks import github_ci, github_delivery, github_retry  # noqa: F401
