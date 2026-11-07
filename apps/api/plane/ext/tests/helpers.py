# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Response readers shared by the epic tests; all read .json(), since .data holds UUID objects."""

import threading

from django.db import connection


def results(response):
    body = response.json()
    if isinstance(body, dict) and "results" in body:
        body = body["results"]
    if isinstance(body, dict):  # grouped results
        rows = []
        for group in body.values():
            rows += group.get("results", []) if isinstance(group, dict) else group
        return rows
    return body


def ids(response):
    return {str(row["id"]) for row in results(response)}


def row_ids(data, found=None):
    """Every value of an `id` key, at any depth."""
    found = set() if found is None else found
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "id" and isinstance(value, str):
                found.add(value)
            else:
                row_ids(value, found)
    elif isinstance(data, list):
        for value in data:
            row_ids(value, found)
    return found


def run_in_threads(count, fn):
    """Run fn in `count` threads started together, each on its own DB connection."""
    barrier = threading.Barrier(count)
    out, errors = [], []

    def target():
        try:
            barrier.wait()
            out.append(fn())
        except Exception as error:  # surfaced to the test below
            errors.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=target) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise errors[0]
    return out
