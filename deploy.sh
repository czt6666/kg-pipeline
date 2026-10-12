#!/usr/bin/env bash
set -euo pipefail

# Deploys kg-pipeline to czt666.cn as a new numbered release, switches the
# `current` symlink to it, and restarts the single Python service. The service now
# serves both pipeline APIs and /api/kg/* graph APIs from the same process.
#
# Server-side layout:
#   apps/kg-pipeline/releases/vN/     immutable release
#   apps/kg-pipeline/current          -> releases/vN
#   apps/kg-pipeline/shared/app.env   TYPE/PORT/START
#   apps/kg-pipeline/shared/data/     persistent ./data symlink target
#
# Usage:
#   ./deploy.sh
#   ./deploy.sh --data
#   ./deploy.sh --env
#   ./deploy.sh --data --env

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
ssh "$HOST" "rm -rf $STAGE && mkdir -p $STAGE/{apps,assistant,core,deploy,eval,graph,prompting,resources,services,src,web}"
for d in apps assistant core eval graph prompting resources services src; do
  rsync -a --exclude='__pycache__' "$d/" "$HOST:$STAGE/$d/"
done
rsync -a config.yaml "$HOST:$STAGE/config.yaml"
rsync -a deploy/requirements-serve.txt "$HOST:$STAGE/requirements.txt"
rsync -a deploy/run.sh "$HOST:$STAGE/run.sh"

echo "==> Syncing built frontend (web/dist/)"
COPYFILE_DISABLE=1 tar czf - -C web/dist . | ssh "$HOST" "mkdir -p $STAGE/web/dist && tar xzf - -C $STAGE/web/dist"

echo "==> Moving staged files into $REL"
ssh "$HOST" "mkdir -p $REL && mv $STAGE/* $REL/ && chmod +x $REL/run.sh && ln -sfn ../../shared/data $REL/data"

if [[ "$SYNC_DATA" == "1" ]]; then
  echo "==> Syncing persistent data/ (can take a while)"
  tar czf - -C . data | ssh "$HOST" "mkdir -p $BASE/shared && tar xzf - -C $BASE/shared"
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
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 https://czt666.cn/api/kg/merged || echo 000)
  if [[ "$code" == "200" ]]; then break; fi
  sleep 2
done
curl -sS -o /dev/null -w "  https://czt666.cn/kg/           -> %{http_code}\n" https://czt666.cn/kg/
curl -sS -o /dev/null -w "  https://czt666.cn/api/kg/merged -> %{http_code}\n" https://czt666.cn/api/kg/merged
if [[ "$code" != "200" ]]; then
  echo "  WARNING: /api/kg/merged did not return 200 after retries -- check: ssh $HOST journalctl -u czt666@$APP -n 50"
fi

echo "Done. Rollback if needed: ssh $HOST 'ln -sfn releases/v<N> $BASE/current && systemctl restart czt666@$APP'"
