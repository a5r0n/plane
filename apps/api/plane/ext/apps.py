# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class SquadronExtConfig(AppConfig):
    name = "plane.ext"
    label = "squadron_ext"

    def ready(self):
        from celery.signals import before_task_publish

        from plane.ext.epics.joins import install
        from plane.ext.provenance import stamp_provenance

        install()
        before_task_publish.connect(stamp_provenance, dispatch_uid="squadron-activity-provenance")
