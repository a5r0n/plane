# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Find work item rows in any list or grouped response, to add our keys to them."""


def issue_rows(data, found=None):
    found = [] if found is None else found
    if isinstance(data, dict):
        if "id" in data and "sequence_id" in data:
            found.append(data)
        for value in data.values():
            issue_rows(value, found)
    elif isinstance(data, list):
        for value in data:
            issue_rows(value, found)
    return found
