#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# CI 状态与正常演示彻底分开，结束后只清理本脚本创建的资源。
task_state_dir="$(mktemp -d)"
mkdir -p logs
export HR_DATA_DIR="$task_state_dir"
export HR_QUERY_BACKEND=sqlite
uv run uvicorn backend.hr.api:app --host 127.0.0.1 --port 8000 > logs/ci-api.log 2>&1 &
task_api_pid=$!
node node_modules/.bin/vinext start --hostname 127.0.0.1 > logs/ci-frontend.log 2>&1 &
task_frontend_pid=$!
cleanup() {
  kill "$task_frontend_pid" "$task_api_pid" 2>/dev/null || true
  wait "$task_frontend_pid" "$task_api_pid" 2>/dev/null || true
  rm -rf "$task_state_dir"
}
trap cleanup EXIT
curl --noproxy '*' --fail --silent --retry 30 --retry-connrefused --retry-delay 1 http://127.0.0.1:3000/api/health > /dev/null
uv run python scripts/smoke_http.py
