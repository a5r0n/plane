**Edit:** `steps` in `ISSUE_DISPLAY_PROPERTIES_KEYS` and `ISSUE_DISPLAY_PROPERTIES`

**Why:** Lists the step chip in the display properties menu

**Edit:** an `oxlint-disable-next-line` on upstream's duplicate `project_id` enum value

**Why:** The pre-commit hook lints a staged file with `--deny-warnings`, so this upstream warning blocks any commit that touches the file
