# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class SquadronExtConfig(AppConfig):
    name = "plane.ext"
    label = "squadron_ext"

    def ready(self):
        from plane.ext.epics.joins import install as install_epic_joins
        from plane.ext.readonly import install as install_read_only

        install_epic_joins()
        install_read_only()
