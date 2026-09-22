#!/bin/bash
set -euo pipefail
# 本脚本只管理该 compose 项目；HR_DOCKER_HOST 可覆盖默认开发引擎地址。
# 保守并行度减少本机压力；up 会构建/初始化，resume 仅恢复已有服务。
lab_root="$(cd "$(dirname "$0")" && pwd)"
export DOCKER_HOST="${HR_DOCKER_HOST:-unix://$HOME/.colima/hr-superset/docker.sock}"
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
    # up 属于自动部署入口，不是手工学习的下一步。先检查 marker，再生成材料。
    if [[ -f "$lab_root/.local/application/manual-learning.json" ]]; then
      echo "正在手工学习，禁止自动初始化。已有平台需要恢复运行时，请用 services.sh resume。"
      exit 1
    fi
    python3 "$lab_root/prepare.py"
    cd "$lab_root/../.."
    uv run python integrations/superset/export.py
    if ! compose up -d --build; then
      compose logs --tail 80 init
      exit 1
    fi
    uv run python integrations/superset/run.py setup
    ;;
  status) compose ps -a ;;
  # 已有容器 start 不经过 init 服务的完整初始化流程，保留用户手工配置。
  resume) compose start postgres superset ;;
  logs) compose logs --tail 60 ;;
  stop) compose stop ;;
  validate)
    # 调用真实接口验收，需事先完成平台配置；与不连接服务的 pytest 单测不同。
    cd "$lab_root/../.."
    uv run python scripts/validate_superset.py
    ;;
  *) echo "Usage: $0 {up|resume|status|logs|stop|validate}"; exit 2 ;;
esac
