**Edit:** Replace upstream's two manifest links with the squadron one (`MANIFEST_LINK`, credentialed)

**Why:** One manifest, fetched with the session cookie, so the app installs from Android Chrome and the iOS Home Screen behind a login proxy

**Edit:** `oxlint-disable`/`oxlint-enable` pair around upstream's font side-effect imports

**Why:** The pre-commit hook lints with `--deny-warnings`, and those upstream imports warn (`import/no-unassigned-import`), so no edit to this file could be committed otherwise
