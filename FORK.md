# FORK.md

`a5r0n/plane` is a thin-hook fork of `makeplane/plane`. Our base branch is `squadron`: an upstream
release tag (now `v1.4.3`) plus our code. All fork work targets it. `preview` only tracks upstream.

## Rules

- Our code lives in our own dirs: backend `apps/api/plane/ext/` (Django app `plane.ext`, label
  `squadron_ext`), frontend `apps/web/core/components/squadron/`, because web code needs the `@/`
  stores, which a separate package can't reach. The backend dir sits inside `plane/` so the prod
  image (which copies only `plane/`) needs no `Dockerfile.api` hook.
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
| `apps/api/plane/settings/common.py` | `plane.ext` in `INSTALLED_APPS` | Registers our app |
| `apps/api/plane/urls.py` | `plane.ext.urls` mounted at `api/`, first | Our routes win over upstream's |
| `.github/workflows/pull-request-build-lint-api.yml` | `squadron` in `pull_request.branches` | PR checks on our base |
| `.github/workflows/pull-request-build-lint-web-apps.yml` | `squadron` in `pull_request.branches` | PR checks on our base |

## Images

`.github/workflows/squadron-images.yml` builds `backend`, `frontend`, `admin`, `space` and `live`
for amd64. PRs to `squadron` only build. Pushes publish to `ghcr.io/a5r0n/plane/<image>`:

- a push to `squadron` as `squadron` and `sha-<short>`;
- a release tag as that same tag and `sha-<short>`.

The packages are private, so pulling them needs a `docker login ghcr.io` with a token that can read
packages.

The proxy has no fork changes, so it stays upstream's image. Upstream's Branch Build CE needs
Docker Hub secrets the fork doesn't have, so it's disabled in the repo's Actions settings rather
than in the file.

## Versions

Versions are `vBASE-squadron.FEATURE.FIX`, for example `v1.4.3-squadron.1.0`. A git tag on
`squadron` is a release.

- `FEATURE`: a new feature, a migration or a breaking change to fork routes.
- `FIX`: bug fixes. A fix release never contains a migration.
- A new upstream base resets both numbers.
- `package.json` stays upstream's.

## Moving to a new upstream base

We don't follow `preview`. We stay on one release tag and move once, when the next upstream
release is out:

```bash
git fetch upstream --tags && git merge <new-release-tag>
# Never hand-merge the lockfile: take the tag's and regenerate it.
git checkout <new-release-tag> -- pnpm-lock.yaml && pnpm install
pnpm install --frozen-lockfile   # must pass
```

Then re-apply any hook whose upstream file moved (`git status` shows modify/delete), run the
checks, and update the hook log.
