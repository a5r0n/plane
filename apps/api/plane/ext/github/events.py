# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Turn one GitHub webhook payload into the rows it should write, without touching the DB."""

# conclusions that make a run, job or status red
FAILED = {"failure", "timed_out", "cancelled", "action_required", "startup_failure", "error"}


def pr_url(repo, number):
    return f"https://github.com/{repo}/pull/{number}"


def _fact(verb, line, pr=None, sha=None, **data):
    return {"verb": verb, "line": line, "pr": pr, "sha": sha, "data": data}


def _pull_request(action, payload):
    pr = payload.get("pull_request") or {}
    number, sha, draft = pr.get("number"), (pr.get("head") or {}).get("sha"), bool(pr.get("draft"))
    if action == "closed":
        if pr.get("merged"):
            merge = pr.get("merge_commit_sha")
            return [_fact("merged", "PR merged", number, sha, merge_sha=merge, base=(pr.get("base") or {}).get("ref"))]
        return [_fact("closed", "PR closed without merging", number, sha)]
    if action == "reopened":
        return [_fact("reopened", "PR reopened", number, sha, draft=draft)]
    if action == "synchronize":
        return [_fact("pushed", f"pushed {sha[:7]}", number, sha, before=payload.get("before"), draft=draft)]
    if action == "ready_for_review":
        return [_fact("draft", "PR marked ready for review", number, sha, draft=False)]
    if action == "converted_to_draft":
        return [_fact("draft", "PR converted to draft", number, sha, draft=True)]
    return []


def _review(action, payload):
    if action != "submitted":
        return []
    pr, review = payload.get("pull_request") or {}, payload.get("review") or {}
    state = (review.get("state") or "").lower()
    words = {"approved": "approved", "changes_requested": "requested changes", "commented": "reviewed"}
    login = (review.get("user") or {}).get("login") or ""
    return [
        _fact(
            "review",
            f"{login} {words.get(state, state)}".strip(),
            pr.get("number"),
            review.get("commit_id") or (pr.get("head") or {}).get("sha"),
            state=state,
            review_url=review.get("html_url"),
            draft=bool(pr.get("draft")),
        )
    ]


def _comment(event, action, payload):
    if action != "created":
        return []
    comment = payload.get("comment") or {}
    if event == "issue_comment":
        issue = payload.get("issue") or {}
        if not issue.get("pull_request"):
            return []
        number, sha = issue.get("number"), None
    else:
        pr = payload.get("pull_request") or {}
        number, sha = pr.get("number"), comment.get("commit_id") or (pr.get("head") or {}).get("sha")
    login = (comment.get("user") or {}).get("login") or ""
    return [_fact("comment", f"{login} commented".strip(), number, sha, comment_url=comment.get("html_url"))]


def _push(payload, repository):
    default = repository.get("default_branch")
    if not default or payload.get("ref") != f"refs/heads/{default}" or payload.get("deleted"):
        return []
    after = payload.get("after") or ""
    return [
        _fact(
            "base-moved", f"{default} moved to {after[:7]}", None, after, before=payload.get("before"), branch=default
        )
    ]


def _run(action, payload):
    run = payload.get("workflow_run") or {}
    if action not in ("requested", "completed"):
        return []
    sha = run.get("head_sha")
    data = {
        "kind": "run",
        "id": run.get("id"),
        "attempt": run.get("run_attempt") or 1,
        "name": run.get("name") or "",
        "status": "completed" if action == "completed" else "pending",
        "conclusion": run.get("conclusion") if action == "completed" else None,
    }
    numbers = [p.get("number") for p in run.get("pull_requests") or [] if p.get("number")]
    line = f"workflow {data['name']} {data['conclusion'] or 'requested'}"
    return [_fact("checks", line, number, sha, **data) for number in numbers] or [
        _fact("checks", line, None, sha, **data)
    ]


def _job(action, payload):
    job = payload.get("workflow_job") or {}
    if action != "completed":
        return []
    data = {
        "kind": "job",
        "id": job.get("id"),
        "run_id": job.get("run_id"),
        "attempt": job.get("run_attempt") or 1,
        "name": job.get("name") or "",
        "conclusion": job.get("conclusion"),
    }
    return [_fact("checks", f"job {data['name']} {data['conclusion']}", None, job.get("head_sha"), **data)]


def _status(payload):
    data = {
        "kind": "status",
        "context": payload.get("context") or "",
        "state": payload.get("state"),
        "at": payload.get("updated_at") or payload.get("created_at"),
    }
    return [_fact("checks", f"status {data['context']} {data['state']}", None, payload.get("sha"), **data)]


def on_default_branch(event, payload, repository):
    """CI on the default branch is not a PR's."""
    default = repository.get("default_branch")
    if event == "workflow_run":
        run = payload.get("workflow_run") or {}
        return run.get("head_branch") == default and not run.get("pull_requests")
    if event == "workflow_job":
        return (payload.get("workflow_job") or {}).get("head_branch") == default
    if event == "status":
        return any(b.get("name") == default for b in payload.get("branches") or [])
    return False


def facts(event, payload):
    """The rows one delivery writes, each {verb, line, pr, sha, data}; pr or sha may be None."""
    action = payload.get("action")
    repository = payload.get("repository") or {}
    if event == "pull_request":
        return _pull_request(action, payload)
    if event == "pull_request_review":
        return _review(action, payload)
    if event in ("issue_comment", "pull_request_review_comment"):
        return _comment(event, action, payload)
    if event == "push":
        return _push(payload, repository)
    if event in ("workflow_run", "workflow_job", "status") and on_default_branch(event, payload, repository):
        return []
    if event == "workflow_run":
        return _run(action, payload)
    if event == "workflow_job":
        return _job(action, payload)
    if event == "status":
        return _status(payload)
    return []


def heads(event, payload):
    """(head sha, PR number) pairs a delivery reveals, for mapping CI events to their PR."""
    if event == "pull_request":
        pr = payload.get("pull_request") or {}
        sha = (pr.get("head") or {}).get("sha")
        return [(sha, pr["number"])] if sha and pr.get("number") else []
    if event == "workflow_run":
        run = payload.get("workflow_run") or {}
        return [
            (run["head_sha"], p["number"])
            for p in run.get("pull_requests") or []
            if run.get("head_sha") and p.get("number")
        ]
    return []
