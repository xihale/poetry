#!/usr/bin/env bash
# Server-side deploy for poetry.xeed.ink — started by scripts/server/webhook.mjs
# (or manually: ssh gx, then
#  `runuser -u poetry-ci -- env HOME=/home/poetry-ci bash ~/poetry/scripts/server/deploy.sh`).
#
# The build is pure (no network beyond npm): the corpus is committed, so this is
#   1. shallow-fetch the pushed branch into the persistent clone
#   2. bun install + corpus-check (are the four artifacts coherent?) + generate
#   3. rsync into /srv/poetry (Caddy serves it). Three trees never delete:
#      /_nuxt/ (content-hashed chunks), /corpus/ (cached immutable by the
#      ?v=CORPUS_BUILD stamp the app puts on every request) and /fonts/
#      (referenced by immutable-cached CSS). They retire into ~/poetry-attic:
#      a page or bundle cached in a browser may still ask for them.
set -Eeuo pipefail
umask 022
REF="${1:-refs/heads/main}"
BRANCH="${REF#refs/heads/}"
REPO=/home/poetry-ci/poetry
DEST=/srv/poetry
LOCK=/home/poetry-ci/.deploy.lock
RERUN=/home/poetry-ci/.deploy-rerun
say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { say "FATAL: $*"; exit 1; }
cd "$REPO"
# One deploy at a time; a push that lands mid-deploy queues exactly one rerun
# (latest commit wins — the queued rerun fetches the newest sha anyway).
exec 9>"$LOCK"
if ! flock -n 9; then
  touch "$RERUN"
  say "deploy already running — queued one rerun"
  exit 0
fi
say "=== deploy start (${BRANCH}, sha=${POETRY_PUSH_SHA:-unknown}) ==="
# The clone is disposable; a stray worktree mutation must not block a checkout.
git reset --hard -q
# Snapshot the running script BEFORE the fetch: bash keeps executing the old
# inode across the checkout, but $0 is just a path and resolves to the new
# file afterwards — path-to-path comparison can never detect the change.
SELF_SNAP=$(mktemp)
cat "$0" > "$SELF_SNAP"
# github.com is intermittently unreachable from this box (blog hit a 134s
# connect timeout between two successful fetches two minutes apart). Retry
# until we hold the exact pushed commit, and never build from a tree we could
# not verify — a silent stale deploy is the worst failure mode. `timeout`
# bounds each attempt (git lets a connect hang >2min otherwise). Note
# `git fetch && git checkout` alone would NOT abort under errexit: a failed
# non-final command of an AND-list is exempt.
WANT="${POETRY_PUSH_SHA:-}"
ok=""
for attempt in 1 2 3 4 5; do
  if timeout 60 git fetch --depth=1 origin "$BRANCH"; then
    got=$(git rev-parse -q --verify FETCH_HEAD || true)
    if [ -z "$WANT" ] || [ "$got" = "$WANT" ]; then ok=1; break; fi
    say "fetch got ${got:-nothing}, want $WANT — attempt $attempt"
  else
    say "fetch failed — attempt $attempt"
  fi
  [ "$attempt" = 5 ] || sleep $((attempt * 5))
done
if [ -z "$ok" ]; then
  die "could not fetch $BRANCH (want ${WANT:-any tip}) — keeping last good deploy"
fi
git checkout -q -B "$BRANCH" FETCH_HEAD
if ! cmp -s "$SELF_SNAP" "$REPO/scripts/server/deploy.sh"; then
  rm -f "$SELF_SNAP"; say "deploy.sh changed — re-execing"
  exec /bin/bash "$REPO/scripts/server/deploy.sh" "$@"
fi
rm -f "$SELF_SNAP"
# --- build -------------------------------------------------------------------
bun install --frozen-lockfile
bun run corpus-check
bun run generate
printf '{"sha":"%s","branch":"%s","deployedAt":"%s"}\n' \
  "$(git rev-parse HEAD)" "$BRANCH" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .output/public/deploy-meta.json
# --- publish ----------------------------------------------------------------
# HTML and anything neither hashed nor stamped replace wholesale. /_nuxt/,
# /corpus/ and /fonts/ retire into a timestamped attic instead of being
# deleted: a browser holds them for a year (immutable) or a week (fonts), and
# attic dirs are pruned by their own age, measured from retirement, independent
# of deploy cadence. $HOME (not /srv/poetry) — the web-served tree is all
# ReadWritePaths grants beside it.
ATTIC="$HOME/poetry-attic"
mkdir -p "$ATTIC"
rsync -a --delete --delay-updates --exclude=/_nuxt --exclude=/corpus --exclude=/fonts \
  --exclude=/deploy-status.json \
  --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  .output/public/ "$DEST/"
# --checksum: generate rewrites .output every time, so mtimes are always fresh
# and quick-check would re-copy (and thus --backup) all 64 MB of corpus every
# deploy; content comparison retires only genuinely replaced files.
for tree in _nuxt corpus fonts; do
  rsync -a --delete --checksum --backup --backup-dir="$ATTIC/$(date -u +%Y%m%dT%H%M%S)" \
    --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
    ".output/public/$tree/" "$DEST/$tree/"
done
# GNU find rounds age up: +6 = 7 full days, comfortably longer than any session
# that crossed a deploy; prune from retirement time.
find "$ATTIC" -mindepth 1 -maxdepth 1 -type d -mtime +6 -exec rm -rf {} +
say "published $(git rev-parse --short HEAD) → $DEST (attic: $(du -sh "$ATTIC" 2>/dev/null | cut -f1))"
say "=== deploy done ==="
if [ -e "$RERUN" ]; then
  rm -f "$RERUN"
  say "a newer push arrived during this deploy — running again"
  exec /bin/bash "$0" "$REF"
fi
