# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Users listed in SQUADRON_READ_ONLY_USER_IDS may only read through the v1 API (API-key auth)."""

import os

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS

from plane.api.middleware.api_authentication import APIKeyAuthentication

SETTING = "SQUADRON_READ_ONLY_USER_IDS"


def read_only_user_ids():
    # read on every request, not cached: tests patch the env per test
    return {part.strip().lower() for part in os.environ.get(SETTING, "").split(",") if part.strip()}


def install():
    original = APIKeyAuthentication.authenticate
    if getattr(original, "squadron_read_only", False):
        return

    def authenticate(self, request):
        result = original(self, request)
        if result and request.method not in SAFE_METHODS and str(result[0].id).lower() in read_only_user_ids():
            raise PermissionDenied("This identity is read-only.")
        return result

    authenticate.squadron_read_only = True
    APIKeyAuthentication.authenticate = authenticate
