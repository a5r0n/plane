**Edit:** import `record_provenance`; call it right after the `bulk_create` in `issue_activity`

**Why:** `bulk_create` skips `post_save`, so this is the only exact link from the task's provenance header to the rows it wrote (FORK.md, Activity API)

**Edit:** `delete_issue_relation_activity` records the inverse type on the other item for `implemented_by` / `implements`

**Why:** The other item's feed names the relation from its own side, as `blocked_by` / `blocking` already do

**Edit:** call `record_provenance` right after the "created the issue" row in `create_issue_activity`

**Why:** That row is made with `IssueActivity.objects.create`, outside the bulk insert, so the call after `bulk_create` never sees it
