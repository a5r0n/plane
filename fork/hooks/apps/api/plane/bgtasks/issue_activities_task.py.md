**Edit:** import `record_provenance`; call it right after the `bulk_create` in `issue_activity`

**Why:** `bulk_create` skips `post_save`, so this is the only exact link from the task's provenance header to the rows it wrote (FORK.md, Activity API)
