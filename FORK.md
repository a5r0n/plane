# FORK.md

`a5r0n/plane` is a thin-hook fork of `makeplane/plane` (branch `preview`).

## Rules

- Our code lives in our own dirs: backend `apps/api/ext/` (Django app `ext`, label
  `squadron_ext`), frontend `packages/squadron` (`@squadron/web`).
- Upstream files get only minimal hook edits: an import, a registration line, a render site.
  Edit upstream directly where a hook won't do.
- Every hook line carries a `squadron` marker comment, so `git grep -n squadron` lists them all.
- Every hook edit is logged below.

## Hook log

| Upstream file | Edit | Why |
|---|---|---|
| _none yet_ | | |

## Merging upstream

```bash
git fetch upstream && git merge upstream/preview
# Never hand-merge the lockfile: take upstream's and regenerate it.
git checkout upstream/preview -- pnpm-lock.yaml && pnpm install
pnpm install --frozen-lockfile   # must pass
```

Then re-apply any hook whose upstream file moved (`git status` shows modify/delete), run the
checks, and update the hook log.

## Merge rehearsal (2026-10-31): thin-hook holds

Branch `rehearsal/thin-hook`: a hook added at upstream `bc2fce4f1b` (2026-08-31), then
`upstream/preview` at `b98e1defb0` (2026-10-29) merged in: 169 commits, 3,190 files changed.

**Hook:** `GET /api/ext/ping/` from `apps/api/ext/` plus a `<SquadronMark />` from
`packages/squadron` in the web help menu footer. 10 own files, 6 upstream files:

| Upstream file | Edit | Merge result |
|---|---|---|
| `apps/api/plane/settings/common.py` | `"ext"` in `INSTALLED_APPS` | clean (file churned 83 lines upstream) |
| `apps/api/plane/urls.py` | `path("api/ext/", include("ext.urls"))` | clean |
| `apps/api/Dockerfile.api` | `COPY ext ext/` (prod image copies only `plane/`) | clean (file rewritten for uv) |
| `apps/web/package.json` | `"@squadron/web": "workspace:*"` | clean |
| `apps/web/.../help-section/root.tsx` | 1 import, 1 render line | **conflict**: upstream moved it out of `core/` and rewrote it on propel (modify/delete) |
| `pnpm-lock.yaml` | generated | **silently broken**: git merged it with no conflict, `pnpm install --frozen-lockfile` failed |

**Cost:** 1 textual conflict (2 lines re-applied at the new path), 1 silent lockfile break
(fixed by taking upstream's lockfile and regenerating: +25 lines, ours only), 0 backend
conflicts. Agent wall time: hook ~5 min, merge and resolve ~1.5 min, verification ~5 min.
After the merge: `@squadron/web` and `web` build, type-check and lint clean; the API unit
suite passes (564, including the ping test); on the dev stack `/api/ext/ping/` returns 200
next to upstream routes; the mark is in the built web bundle.

**Cheaper another way:**
- Lockfile: never merge it; regenerate it (now the procedure above). This was the only
  failure git didn't report.
- Frontend render sites cost the most: upstream is moving and rewriting web components
  (3 of the 169 commits moved or rewrote that one file). Keep render sites few, in the least-churned
  file that works.
- `apps/api/ext/` needs a hook in `Dockerfile.api`, because the prod image copies only
  `plane/`. Putting the app at `apps/api/plane/ext/` would drop that hook; open choice.

**Not covered:** models and migrations (an `ext` migration chain depending on upstream's
latest migration), larger hooks, and a browser check of the rendered mark.
