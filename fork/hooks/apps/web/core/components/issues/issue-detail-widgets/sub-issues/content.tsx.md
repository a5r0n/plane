**Edit:** `handleFetchSubIssues` turns `issue_visibility` on only if it's still off after the fetch

**Why:** StrictMode's double effect toggled the list back to hidden in dev
