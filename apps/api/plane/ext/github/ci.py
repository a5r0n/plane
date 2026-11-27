# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The CI verdict for one PR head, from its hidden `checks` rows."""

from plane.ext.github.events import FAILED

SETTLE = 30  # seconds after the last completion before a verdict is written
PASSED, FAILED_VERDICT, DIDNT_RUN = "passed", "failed", "didn't run"


def verdict(checks):
    """checks: [(created_at, data)] oldest first. Returns None (no CI), ("pending", None) or (verdict, failed names)."""
    runs, jobs, statuses = {}, {}, {}
    for _, data in checks:
        kind = data.get("kind")
        if kind == "run":
            run_id, attempt = data.get("id"), data.get("attempt") or 1
            current = runs.get(run_id)
            # a newer attempt replaces the run; within one attempt, completed wins whatever the order
            if (
                current is None
                or attempt > current["attempt"]
                or (attempt == current["attempt"] and data.get("status") == "completed")
            ):
                runs[run_id] = data
        elif kind == "job":
            jobs[data.get("id")] = data
        elif kind == "status":
            context = data.get("context")
            if context not in statuses or (data.get("at") or "") >= (statuses[context].get("at") or ""):
                statuses[context] = data
    # a run seen only through its jobs counts by the jobs of its latest attempt
    latest = {}
    for job in jobs.values():
        latest[job.get("run_id")] = max(latest.get(job.get("run_id"), 0), job.get("attempt") or 1)
    for run_id, run in runs.items():
        latest[run_id] = max(latest.get(run_id, 0), run.get("attempt") or 1)
    if not runs and not jobs and not statuses:
        return None
    if any(run.get("status") != "completed" for run in runs.values()):
        return ("pending", None)
    if any(status.get("state") == "pending" for status in statuses.values()):
        return ("pending", None)

    failed, green = [], False
    for job in jobs.values():
        if (job.get("attempt") or 1) != latest[job.get("run_id")]:
            continue
        if job.get("conclusion") in FAILED:
            failed.append(job.get("name"))
        elif job.get("conclusion") == "success":
            green = True
    for run_id, run in runs.items():
        if (run.get("attempt") or 1) != latest[run_id]:
            continue
        if run.get("conclusion") in FAILED:
            named = any(
                j.get("run_id") == run_id
                and j.get("conclusion") in FAILED
                and (j.get("attempt") or 1) == latest[run_id]
                for j in jobs.values()
            )
            if not named:
                failed.append(run.get("name"))
        elif run.get("conclusion") == "success":
            green = True
    for context, status in statuses.items():
        if status.get("state") in FAILED:
            failed.append(context)
        elif status.get("state") == "success":
            green = True
    if failed:
        return (FAILED_VERDICT, sorted(set(failed)))
    return (PASSED, []) if green else (DIDNT_RUN, [])


def line(result, failed):
    if result == FAILED_VERDICT:
        return "CI failed: " + ", ".join(failed)
    return f"CI {result}"
