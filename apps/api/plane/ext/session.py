# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework.views import APIView

from plane.authentication.session import BaseSessionAuthentication


class Session:
    """The web app's twin of a v1 view: session auth and the app's default throttles."""

    authentication_classes = [BaseSessionAuthentication]

    def get_throttles(self):
        return APIView.get_throttles(self)
