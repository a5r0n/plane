#!/bin/bash
# Checks the hook log in fork/hooks/ against the `squadron` markers in upstream files (see FORK.md).
set -eu
cd "$(git rev-parse --show-toplevel)"

fail=0

# Upstream files with a marker comment; our own dirs are excluded.
marked=$(git grep -lE '(#|//|/\*|<!--) *squadron' -- . \
  ':!apps/api/plane/ext' ':!apps/web/core/components/squadron' ':!apps/live/src/squadron' \
  ':!tests/e2e' ':!fork' ':!FORK.md' ':!.github/workflows/squadron-*' ':!docker-compose-e2e.yml' \
  ':!docker-compose-squadron.yml' || true)

for f in $marked; do
  if [ ! -f "fork/hooks/$f.md" ]; then
    echo "missing log: $f has a squadron marker but no fork/hooks/$f.md"
    fail=1
  fi
done

for log in $(git ls-files 'fork/hooks/*.md'); do
  f=${log#fork/hooks/}
  f=${f%.md}
  if [ ! -f "$f" ]; then
    echo "stale log: $log names $f, which doesn't exist"
    fail=1
  fi
done

[ "$fail" = 0 ] && echo "hook log OK"
exit "$fail"
