#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "$(git status --porcelain)" ]]; then
  printf 'Please commit or resolve working tree changes before packaging a release.\n' >&2
  exit 1
fi
uv run ruff check backend tests scripts integrations/superset
uv run pytest -q
npm run typecheck
npm run lint
npm run build
bash scripts/ci-smoke.sh
mkdir -p releases
task_commit="$(git rev-parse --short HEAD)"
git archive --format=tar.gz --output="releases/chengguan-hr-${task_commit}.tar.gz" HEAD
printf 'Source release ready: releases/chengguan-hr-%s.tar.gz\n' "$task_commit"
printf 'Run npm run demo:production on the target LM Studio host after installing dependencies.\n'
