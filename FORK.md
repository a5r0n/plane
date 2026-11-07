# FORK.md

`a5r0n/plane` is a thin-hook fork of `makeplane/plane`. Our base branch is `squadron`: an upstream
release tag (now `v1.4.3`) plus our code. All fork work targets it. `preview` only tracks upstream.

## Rules

- Our code lives in our own dirs: backend `apps/api/plane/ext/` (Django app `plane.ext`, label
  `squadron_ext`), frontend `apps/web/core/components/squadron/`, because web code needs the `@/`
  stores, which a separate package can't reach, and live server `apps/live/src/squadron/`. The
  backend dir sits inside `plane/` so the prod image (which copies only `plane/`) needs no
  `Dockerfile.api` hook.
- Upstream files get only minimal hook edits: an import, a registration line, a render site.
  Edit upstream directly where a hook won't do.
- Keep frontend render sites few, each in the least-churned upstream file that works: upstream
  keeps moving and rewriting web components, and render sites are where merges conflict.
- Every hook line carries a `squadron` marker comment where the file format allows one, so
  `git grep -n squadron` lists them. Dockerfiles take only whole-line comments: put `# squadron`
  on the line above. JSON (`package.json`, the lockfile) takes none: the hook log is the record.
- Every hook edit is logged below.

## Hook log

| Upstream file                                            | Edit                                             | Why                              |
| -------------------------------------------------------- | ------------------------------------------------ | -------------------------------- |
| `apps/api/plane/settings/common.py`                      | `plane.ext` in `INSTALLED_APPS`                  | Registers our app                |
| `apps/api/plane/urls.py`                                 | `plane.ext.urls` mounted at `api/`, first        | Our routes win over upstream's   |
| `.github/workflows/pull-request-build-lint-api.yml`      | `squadron` in `pull_request.branches`            | PR checks on our base            |
| `.github/workflows/pull-request-build-lint-web-apps.yml` | `squadron` in `pull_request.branches`            | PR checks on our base            |
| `apps/live/src/controllers/index.ts`                     | `SquadronPageContentController` in `CONTROLLERS` | Registers the page content route |
| `pnpm-workspace.yaml`                                    | `tests/e2e` in `packages`                        | Makes the E2E suite a package    |

## Pages API

`plane.ext` serves project pages on the v1 API (API key) at the paths `plane_sdk` calls:

- `workspaces/<slug>/projects/<id>/pages/`: list (paginated, child and archived pages included)
  and create (`name` and `description_html` required, optional `parent_id`);
- `.../pages/<page_id>/`: retrieve, update (PUT or PATCH) and delete (archived pages only);
- `.../pages/<page_id>/archive/`: POST archives, DELETE restores.

Permissions are the web app's (`ProjectPagePermission`; guests see only their own pages unless the
project lets guests view everything). Archive, restore and delete reuse upstream's `PageViewSet`.

The live server owns a page's document, so an update that changes `description_html` or `name`
goes through it: the API posts the new content and the stored document to
`<LIVE_URL>/squadron/pages/<page_id>/content/` (`apps/live/src/squadron/`). Live edits the
loaded document in place, so open editors see the change, or the stored state if nobody has the
page open, and returns the formats the API stores. If live can't be reached, the update answers
502 and writes nothing. Locked and archived pages refuse updates.

Needs on the API: `LIVE_BASE_URL` (and `LIVE_BASE_PATH` if not `/live/`) pointing at the live
server, and the same `LIVE_SERVER_SECRET_KEY` as live. Known limits: with several live replicas,
a page open only on another replica is written from the stored state, so its editors don't see the
change and their next save overwrites it; and an editor save already in flight when the API writes
can land after it.

## Images

`.github/workflows/squadron-images.yml` builds `backend`, `frontend`, `admin`, `space` and `live`
for amd64. PRs to `squadron` only build, and there the E2E job builds `backend` and `live`. Pushes
publish to `ghcr.io/a5r0n/plane/<image>`:

- a push to `squadron` as `squadron` and `sha-<short>`;
- a release tag as that same tag and `sha-<short>`.

The packages are public, so pulling them needs no login.

The proxy has no fork changes, so it stays upstream's image. Upstream's Branch Build CE needs
Docker Hub secrets the fork doesn't have, so disable it in the repo's Actions settings rather than
in the file.

## Backend tests

`.github/workflows/squadron-tests.yml` runs the full Django suite from `docker-compose-test.yml` on
every PR to `squadron`, as the `Backend tests` check. No test is skipped.

The default `API_KEY_RATE_LIMIT` (`60/minute`) fails these tests at `v1.4.3` with a 429, so the
workflow raises it in the env file it generates:

- `plane/tests/contract/api/test_projects.py::TestProjectListCreateAPIEndpoint::test_list_relational_order_by_injection_does_not_500`
- `plane/tests/contract/api/test_projects_lite.py::TestProjectsLite::test_returns_paginated_results`
- `plane/tests/contract/api/test_projects_lite.py::TestProjectsLite::test_returns_only_lite_fields`
- `plane/tests/contract/api/test_projects_lite.py::TestProjectsLite::test_archived_excluded_by_default`
- `plane/tests/contract/api/test_projects_lite.py::TestProjectsLite::test_include_archived_returns_all`

Every `api_key_client` test uses the same token, so they share one throttle bucket in Redis, and
which tests go over depends on how fast the run is. A local run with the default limit can fail
others. Set the same value in `apps/api/.env` to match CI.

## E2E

The `E2E` job in `squadron-images.yml` brings up `docker-compose-e2e.yml` on every PR to
`squadron` from the images it just built (db, valkey, rabbitmq, api, live; the db on tmpfs,
migrations once) and runs the TypeScript suite in `tests/e2e`. It skips the stack, but still
builds, when a PR touches none of `apps/api`, `apps/live`, `packages`, `tests/e2e`, the compose
file, the lockfile or the workflow.

The suite sets the stack up over HTTP as a new user would (instance admin, sign-in, workspace,
API token, project), then checks cross-service flows:

- `tests/pages.test.ts`: project pages between the v1 API and an editor-like Hocuspocus client
  (same URL, token and cookie as the web editor).
- `tests/mcp.test.ts`: a smoke run of `plane-mcp-server`, pinned by SHA in `src/mcp.ts`, over
  stdio.

Add a flow as a new `tests/<area>.test.ts`; `inject("stack")` gives it the user, workspace,
project and API key. To run it locally (needs Node, pnpm and `uv`):

```bash
docker compose -f docker-compose-e2e.yml up -d --build --wait
pnpm install && pnpm --filter @plane/e2e test
docker compose -f docker-compose-e2e.yml down
```

`E2E_API_PORT` and `E2E_LIVE_PORT` move the published ports (18000, 13100); point the suite at
them with `E2E_API_URL` and `E2E_LIVE_URL`.

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
