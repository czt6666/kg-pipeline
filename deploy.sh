#!/usr/bin/env bash
set -euo pipefail

# Deploys kg-pipeline to czt666.cn as a new numbered release, switches the
# `current` symlink to it, and restarts the systemd unit. nginx (/kg/, /api/
# -> 127.0.0.1:8787) and the systemd template unit (czt666@.service) are
# already set up on the server and are not touched here.
#
# Server-side layout (a convention shared by every app under /srv/czt666/apps/,
# not specific to this repo -- see /etc/systemd/system/czt666@.service):
#   apps/kg-pipeline/releases/vN/  one immutable release per deploy (own .venv)
#   apps/kg-pipeline/current       -> releases/vN symlink; run.sh/systemd use this
#   apps/kg-pipeline/shared/app.env   TYPE/PORT/START, not touched by this script
#   apps/kg-pipeline/shared/data/     data/work/, persisted across releases --
#                                     symlinked into each release as ./data (see
#                                     --data flag; skipped by default, slow)
#
# The server has ~1.7GB RAM, not enough to reliably run `npm install`/`vite
# build` itself, so the frontend is always built locally and the built dist/
# is what gets pushed -- never node_modules or source .jsx.
#
# Usage:
#   ./deploy.sh              # new release: code + frontend, reuses current
#                             # release's .env, rebuilds venv, restarts service
#   ./deploy.sh --data       # also resync shared data/work/ (slow, ~1.3GB;
#                             # only needed after re-running a pipeline stage
#                             # locally -- new releases always symlink to it,
#                             # this flag just refreshes its contents)
#   ./deploy.sh --env        # push local .env instead of reusing the previous
#                             # release's (only needed after rotating/adding a
#                             # key) -- required on a genuinely first deploy,
#                             # since there's no previous release to reuse from
#   ./deploy.sh --data --env # both

HOST=root@8.130.54.51
APP=kg-pipeline
BASE=/srv/czt666/apps/$APP
cd "$(dirname "$0")"

SYNC_DATA=0
SYNC_ENV=0
for arg in "$@"; do
  case "$arg" in
    --data) SYNC_DATA=1 ;;
    --env) SYNC_ENV=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$SYNC_ENV" == "0" ]] && ! ssh "$HOST" "test -e $BASE/current/.env" 2>/dev/null; then
  echo "no .env on the current release to reuse -- pass --env for a first deploy" >&2
  exit 1
fi

echo "==> Building frontend locally"
(cd web && npm run build)

echo "==> Determining next release number"
LAST=$(ssh "$HOST" "ls $BASE/releases 2>/dev/null | grep -E '^v[0-9]+\$' | sed 's/v//' | sort -n | tail -1")
NEXT=$(( ${LAST:-0} + 1 ))
REL="$BASE/releases/v$NEXT"
echo "    -> v$NEXT"

echo "==> Staging release on the server"
STAGE=/tmp/kg_deploy_stage
ssh "$HOST" "rm -rf $STAGE && mkdir -p $STAGE/src $STAGE/schema $STAGE/prompts $STAGE/eval $STAGE/web"
rsync -a --exclude='__pycache__' src/ "$HOST:$STAGE/src/"
rsync -a schema/ "$HOST:$STAGE/schema/"
rsync -a prompts/ "$HOST:$STAGE/prompts/"
rsync -a eval/ "$HOST:$STAGE/eval/"
rsync -a config.yaml "$HOST:$STAGE/config.yaml"
rsync -a deploy/requirements-serve.txt "$HOST:$STAGE/requirements.txt"
rsync -a deploy/run.sh "$HOST:$STAGE/run.sh"

echo "==> Syncing built frontend (web/dist/)"
# tar+ssh, not rsync/scp: this Mac's built-in openrsync hits a protocol interop
# bug against the server's GNU rsync on minified JS bundles (reliably
# reproduced during initial deploy). tar over ssh sidesteps it. (The "Ignoring
# unknown extended header keyword ...apple.provenance" warnings below are
# harmless macOS metadata GNU tar doesn't recognize.)
COPYFILE_DISABLE=1 tar czf - -C web/dist . | ssh "$HOST" "mkdir -p $STAGE/web/dist && tar xzf - -C $STAGE/web/dist"

echo "==> Moving staged files into $REL"
ssh "$HOST" "mkdir -p $REL && mv $STAGE/* $REL/ && chmod +x $REL/run.sh && ln -sfn ../../shared/data $REL/data"

if [[ "$SYNC_DATA" == "1" ]]; then
  echo "==> Syncing shared data/work/ (can take a while, ~1.3GB -- tar+ssh, see above)"
  tar czf - -C data work | ssh "$HOST" "mkdir -p $BASE/shared/data && tar xzf - -C $BASE/shared/data"
fi

if [[ "$SYNC_ENV" == "1" ]]; then
  echo "==> Pushing local .env into the new release"
  scp .env "$HOST:$REL/.env"
else
  echo "==> Reusing .env from the current release"
  ssh "$HOST" "cp $BASE/current/.env $REL/.env"
fi
ssh "$HOST" "chmod 600 $REL/.env"

echo "==> Building venv (uv)"
ssh "$HOST" "
  export PATH=\$PATH:/root/.local/bin
  mise trust /srv/czt666/.mise.toml >/dev/null 2>&1 || true
  cd $REL
  uv venv --python 3.10 .venv
  uv pip install --python .venv/bin/python -r requirements.txt
"

echo "==> Cutting over: current -> v$NEXT"
ssh "$HOST" "
  cd $BASE
  ln -sfn releases/v$NEXT current_new
  mv -Tf current_new current
  systemctl restart czt666@$APP
  sleep 1
  systemctl is-active czt666@$APP
"

echo "==> Verifying (retrying briefly -- restart can take a moment)"
for i in 1 2 3 4 5; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 https://czt666.cn/api/merged || echo 000)
  if [[ "$code" == "200" ]]; then break; fi
  sleep 2
done
curl -sS -o /dev/null -w "  https://czt666.cn/kg/        -> %{http_code}\n" https://czt666.cn/kg/
curl -sS -o /dev/null -w "  https://czt666.cn/api/merged -> %{http_code}\n" https://czt666.cn/api/merged
if [[ "$code" != "200" ]]; then
  echo "  WARNING: /api/merged did not return 200 after retries -- check: ssh $HOST journalctl -u czt666@$APP -n 50"
fi

echo "Done. Rollback if needed: ssh $HOST 'ln -sfn releases/v<N> $BASE/current && systemctl restart czt666@$APP'"
