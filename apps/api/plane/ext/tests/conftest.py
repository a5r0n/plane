# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# reuse the upstream suite's fixtures, which only apply under plane/tests
from plane.tests.conftest import (  # noqa: F401
    api_client,
    api_key_client,
    api_token,
    create_user,
    user_data,
    workspace,
)
