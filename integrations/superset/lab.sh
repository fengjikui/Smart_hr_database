#!/bin/bash
set -euo pipefail
lab_root="$(cd "$(dirname "$0")" && pwd)"
export DOCKER_HOST="${HR_LAB_DOCKER_HOST:-unix://$HOME/.colima/hr-superset/docker.sock}"
export COMPOSE_PARALLEL_LIMIT=1
compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f "$lab_root/compose.yaml" "$@"
  else
    docker compose -f "$lab_root/compose.yaml" "$@"
  fi
}
case "${1:-status}" in
  up)
    python3 "$lab_root/prepare.py"
    compose up -d --build
    ;;
  status) compose ps -a ;;
  logs) compose logs --tail 60 ;;
  stop) compose stop ;;
  validate)
    cd "$lab_root/../.."
    uv run python integrations/superset/validate.py
    ;;
  *) echo "Usage: $0 {up|status|logs|stop|validate}"; exit 2 ;;
esac
