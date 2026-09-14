#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
uv run uvicorn backend.hr.api:app --host 127.0.0.1 --port 8000 > logs/ci-api.log 2>&1 &
task_api_pid=$!
npm run start > logs/ci-frontend.log 2>&1 &
task_frontend_pid=$!
trap 'kill "$task_frontend_pid" "$task_api_pid" 2>/dev/null || true' EXIT
curl --noproxy '*' --fail --silent --retry 30 --retry-connrefused --retry-delay 1 http://127.0.0.1:3000/api/health > /dev/null
uv run python scripts/smoke_http.py

uv run python scripts/smoke_v2.py
