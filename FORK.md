# FORK.md

`a5r0n/plane` is a thin-hook fork of `makeplane/plane`. Our base branch is `squadron`: an upstream
release tag (now `v1.4.3`) plus our code. All fork work targets it. `preview` only tracks upstream.

## Rules

- Our code lives in our own dirs: backend `apps/api/plane/ext/` (Django app `plane.ext`, label
  `squadron_ext`), frontend `apps/web/core/components/squadron/` plus route modules under
  `apps/web/app/(all)/...` (registered in `app/routes/extended.ts`), because web code needs the `@/`
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

| Upstream file                                                                 | Edit                                                | Why                              |
| ----------------------------------------------------------------------------- | --------------------------------------------------- | -------------------------------- |
| `apps/api/plane/settings/common.py`                                           | `plane.ext` in `INSTALLED_APPS`                     | Registers our app                |
| `apps/api/plane/urls.py`                                                      | `plane.ext.urls` mounted at `api/`, first           | Our routes win over upstream's   |
| `.github/workflows/pull-request-build-lint-api.yml`                           | `squadron` in `pull_request.branches`               | PR checks on our base            |
| `.github/workflows/pull-request-build-lint-web-apps.yml`                      | `squadron` in `pull_request.branches`               | PR checks on our base            |
| `apps/live/src/controllers/index.ts`                                          | `SquadronPageContentController` in `CONTROLLERS`    | Registers the page content route |
| `apps/api/plane/bgtasks/page_version_task.py`                                 | `page.description` → `page.description_json`        | Upstream bug: page versions fail |
| `apps/api/plane/db/models/issue.py`                                           | `apply_epic_scope` import; `IssueManager` via it    | Epic scope on `issue_objects`    |
| `apps/api/plane/app/serializers/issue.py`                                     | `type_id` in `IssueSerializer` fields               | Clients tell epics apart         |
| `apps/api/plane/utils/grouper.py`                                             | `type_id` in `required_fields`                      | Clients tell epics apart         |
| `apps/api/plane/app/views/issue/base.py`                                      | `type_id` in three `.values()` lists                | Clients tell epics apart         |
| `apps/api/plane/app/views/issue/sub_issue.py`                                 | `type_id` in the sub-issue `.values()`              | Clients tell epics apart         |
| `apps/web/app/routes/extended.ts`                                             | Epics route nested in core's layout chain           | Epics page                       |
| `apps/web/core/components/workspace/sidebar/project-navigation.tsx`           | Epics item in the project sidebar                   | Epics page                       |
| `apps/web/core/store/issue/project/issue.store.ts`                            | Optional `serviceType` constructor argument         | Epics list uses `epics/`         |
| `apps/web/core/store/issue/root.store.ts`                                     | `projectEpics` built with `EIssueServiceType.EPICS` | Epics list uses `epics/`         |
| `apps/web/core/store/issue/issue-details/issue.store.ts`                      | `/browse` loads epics into `issueDetail`            | Epic detail fills its widgets    |
| `apps/web/core/components/epic-modal/modal.tsx`                               | Name-only create form in upstream's empty stub      | Epic create                      |
| `apps/web/core/components/issues/issue-layouts/empty-states/project-epic.tsx` | Empty state in upstream's empty stub                | No blank epics page              |
| `pnpm-workspace.yaml`                                                         | `tests/e2e` in `packages`                           | Makes the E2E suite a package    |

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

## Search API

`plane.ext` shadows the v1 work item search (`workspaces/<slug>/work-items/search/` and the legacy
`.../issues/search/`) with `plane/ext/search.py`. On top of upstream's matches (name, project
identifier, whole-number sequence id) it also matches the description and non-deleted comments,
case-insensitively. Results rank title matches first, then description, then comment, newest
first within each, and each carries `matched`: `title`, `description` or `comment`. Parameters
and membership rules are upstream's. The matching is an unindexed `icontains` scan. Session search
and the web app's search are unchanged.

## Relations API

`plane.ext` adds the route `plane_sdk`'s `work_items.relations.delete` calls, which upstream's v1 API
lacks: `POST workspaces/<slug>/projects/<id>/work-items/<id>/relations/remove/` with
`{"related_issue": "<work item id>"}`. It subclasses upstream's `IssueRelationViewSet`, keeping its
permissions (`ProjectEntityPermission`: project members and admins) with API-key auth. A pair of work
items holds one stored relation, so removing it from either item removes it from both, and the
activity on both items records the removal. The relation type is read from the stored relation, so
callers send only `related_issue`. It answers 204, 400 without a valid `related_issue`, and 404 when
the work item isn't in the project or the pair has no relation.

## Epics

An epic is a work item whose type has `is_epic` set. `plane.ext` creates one `Epic` type per
project on first use, and children point at the epic through `parent`, as sub-work-items do. No
migration: the type and parent columns are upstream's.

Session routes, `workspaces/<slug>/projects/<id>/`:

- `epics/` lists and creates epics; `epics/<id>/` and the `epics/<id>/...` sub-routes (`issues/`
  for children, `links/`, `comments/`, `history/`, `archive/` and the rest) reuse upstream's work
  item views (`plane/ext/epics/routes.py` lists them);
- history, comments and activity on an epic come back with `epic` in place of `issue` in the
  activity names.

v1 routes (API key), same prefix:

- `epics/`: GET lists epics in upstream's paginated shape, POST creates one (any parent allowed);
  `external_id` lookups find epics only;
- `epics/<id>/`: GET only, 404 for a work item that isn't an epic. Updates and deletes go through
  `work-items/<id>/`, where `parent` may be an epic;
- `epics/<id>/issues/`: GET lists children (paginated); POST `{"work_item_ids": [...]}` makes
  them children and answers the list of them. It checks every id before writing any: an id that is
  the epic, one of its parents, not a UUID or not a work item in the project answers 400 naming it.

Hiding works only on GET and only on the routes `HIDE` in `routes.py` names; every other route
shows epics as upstream would. The named list routes (work item lists, boards, cycle and module
issues, search) drop epics, and the named count routes (analytics, cycle and module totals and
progress, project and user stats, the v1 project summary) leave them out of every number.
`entity-search/` keeps showing them, for mentions. Session list responses carry `type_id`.

How the hiding works, for anyone merging upstream:

- the `issue_objects` manager filters by a request scope (`exclude`, `only`, `all`); outside a
  scope, which includes background tasks, it shows everything. `objects` is never filtered;
- in `exclude`, joins from cycle and module links and from projects skip epics
  (`plane/ext/epics/joins.py`, installed at app start), since upstream counts over those joins;
- the v1 project summary is replaced by a subclass that subtracts epics from `issues`;
- `plane/ext/tests/test_epic_sweep.py` requests every GET route with and without an epic and fails
  on any route that shows it or whose numbers move, unless the tables in `routes.py` name it. Run it
  after moving to a new base: new upstream routes land there.

Web: an Epics entry in the project sidebar opens `projects/<id>/epics`, which renders upstream's
five layouts against the `projectEpics` store (`apps/web/core/components/squadron/epics/`). "Add
epic" and the empty state open a name-only create form. An epic opens on the normal
`/browse/KEY-N` page, which picks the epic view from `is_epic`.

Notifications, exports and webhooks treat an epic as a work item: subscribers are notified, exports
include it as a row, and `issue` webhooks fire with `type` set to the epic type's id.

Known limits:

- archived epics have no list of their own;
- session `epics/<id>/` and `epics/list/` accept any work item id, epic or not;
- the project detail routes (`projects/<id>/`, `projects/details/`) count epics in
  `next_work_item_sequence`, since epics take sequence numbers;
- exports have no type column, so an epic can't be told from a work item there.
- the epics page shares its layout and display filters with the work items page, so changing one
  changes the other;
- on the epics page, breadcrumbs say "Work Items" and quick-add rows say "work item";
- "Add existing" on an epic offers other epics, so epics can nest.

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
