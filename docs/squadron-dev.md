# Local dev stack for a worktree

Run Plane from source in any worktree of this repo to check a change: backend in Docker
(upstream `docker-compose-local.yml` plus `docker-compose-squadron.yml`), web app on the host.

- One stack per machine. The override pins the compose project to `plane-dev`, so `up` from any
  worktree reuses the same containers and volumes; the API serves the code of the worktree that
  last ran `up`.
- Ports are bound to `127.0.0.1`: API `:8000`, web `:3000`, Postgres `:5432`, Valkey `:6379`,
  MinIO `:9000`/`:9090`.
- Use the local Docker daemon (`docker context use default`, or add `--context default`).

## Setup (once per worktree)

```bash
./setup.sh   # writes the .env files and runs pnpm install
```

`setup.sh` generates a new Django `SECRET_KEY` per worktree, so after switching worktrees you
must log in again.

## Up

Every `docker compose` command below runs from the worktree root with this set in the shell:

```bash
export COMPOSE_FILE=docker-compose-local.yml:docker-compose-squadron.yml
```

```bash
docker compose up -d --build
for i in $(seq 120); do curl -sf -m 5 -o /dev/null http://127.0.0.1:8000/api/instances/ && break; sleep 5; done
curl -sf -m 5 -o /dev/null http://127.0.0.1:8000/api/instances/ \
  || { echo "API did not come up; logs:" >&2; docker compose logs --tail 30 migrator api; false; }
pnpm turbo run dev --filter=web   # http://localhost:3000, hot reload; add --filter=admin for god-mode
```

The first `up` builds the API image and runs all migrations, which takes a few minutes.

## Seed a test user (once per stack)

Creates `dev@plane.local` / `plane-dev-123`, who is the instance admin and the owner of an
onboarded workspace at `/dev`. Running it again is safe. `clear_cache` is required, or the web
app keeps showing the instance-setup screen.

```bash
docker compose exec -T api python manage.py shell <<'EOF'
from plane.db.models import User, Profile, Workspace, WorkspaceMember
from plane.license.models import Instance, InstanceAdmin
from plane.bgtasks.workspace_seed_task import workspace_seed
u, _ = User.objects.get_or_create(email="dev@plane.local", defaults={"username": "dev", "first_name": "Dev", "is_email_verified": True})
u.set_password("plane-dev-123"); u.save()
ws, new = Workspace.objects.get_or_create(slug="dev", defaults={"name": "Dev", "owner": u})
WorkspaceMember.objects.get_or_create(workspace=ws, member=u, defaults={"role": 20})
if new: workspace_seed(ws.id)
Profile.objects.update_or_create(user=u, defaults={"is_onboarded": True, "is_tour_completed": True, "last_workspace_id": ws.id, "onboarding_step": {"profile_complete": True, "workspace_create": True, "workspace_invite": True, "workspace_join": True}})
i = Instance.objects.first(); i.is_setup_done = True; i.is_signup_screen_visited = True; i.save()
InstanceAdmin.objects.get_or_create(user=u, instance=i, defaults={"role": 20})
EOF
docker compose exec -T api python manage.py clear_cache
```

Log in at http://localhost:3000 with that email and password.

## Tests

Backend (a separate throwaway stack on tmpfs; stop the dev stack first to save RAM):

```bash
docker compose stop
docker compose -f docker-compose-test.yml run --rm --build api-tests pytest -m unit   # or plain `pytest` for the full suite
docker compose -f docker-compose-test.yml down -v
```

Frontend (vitest in `live`, `@plane/blocks`, `@plane/editor`, `@plane/services`, `@plane/codemods`).
Stop the web dev server and the dev stack first: with them running, the `@plane/blocks` DOM
tests can run out of memory and time out.

```bash
pnpm turbo run test                          # all
pnpm turbo run test --filter=@plane/services # one package
```

See `AGENTS.md` and `apps/api/tests/RUNNING_TESTS.md` for more.

## Down

```bash
docker compose down      # stop; keeps the database and the seeded user
docker compose down -v   # wipe all data; re-seed after the next up
```

Plain `down` is the default. Wipe with `down -v` when a branch's migrations conflict with the
data left by another branch.
