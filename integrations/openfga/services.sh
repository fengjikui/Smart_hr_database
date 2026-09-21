#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
if [[ -n "${HR_DOCKER_HOST:-}" ]]; then
  export DOCKER_HOST="$HR_DOCKER_HOST"
elif [[ -z "${DOCKER_HOST:-}" && -S "$HOME/.colima/hr-superset/docker.sock" ]]; then
  export DOCKER_HOST="unix://$HOME/.colima/hr-superset/docker.sock"
fi
export COMPOSE_PARALLEL_LIMIT=1
compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f integrations/openfga/compose.yaml "$@"
  else
    docker compose -f integrations/openfga/compose.yaml "$@"
  fi
}
case "${1:-status}" in
  up)
    uv run python -m integrations.openfga.run prepare
    compose up -d
    uv run python -m integrations.openfga.run ready
    ;;
  status) compose ps -a ;;
  logs) compose logs --tail 40 ;;
  stop) compose stop ;;
  resume) compose start postgres openfga ;;
  *) echo 'Usage: services.sh {up|status|logs|stop|resume}'; exit 2 ;;
esac
