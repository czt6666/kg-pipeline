#!/usr/bin/env bash
set -euo pipefail
# Systemd (czt666@kg-pipeline.service, template unit shared by every app under
# /srv/czt666/apps/) execs this from inside the release dir pointed to by the
# `current` symlink. Not kg-pipeline-specific: TYPE/PORT/START come from the
# app-level shared/app.env, so this same script works for any app following
# the apps/<name>/{releases,shared,current} convention.
cd "$(dirname "$0")"
source ../../shared/app.env
exec .venv/bin/python $START
