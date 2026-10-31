# FORK.md

`a5r0n/plane` is a thin-hook fork of `makeplane/plane` (branch `preview`).

## Rules

- Our code lives in our own dirs: backend `apps/api/plane/ext/` (Django app `plane.ext`, label
  `squadron_ext`), frontend `packages/squadron` (`@squadron/web`). The backend dir sits inside
  `plane/` so the prod image (which copies only `plane/`) needs no `Dockerfile.api` hook.
- Upstream files get only minimal hook edits: an import, a registration line, a render site.
  Edit upstream directly where a hook won't do.
- Keep frontend render sites few, each in the least-churned upstream file that works: upstream
  keeps moving and rewriting web components, and render sites are where merges conflict.
- Every hook line carries a `squadron` marker comment where the file format allows one, so
  `git grep -n squadron` lists them. Dockerfiles take only whole-line comments: put `# squadron`
  on the line above. JSON (`package.json`, the lockfile) takes none: the hook log is the record.
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
