#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check backend tests scripts
uv run pytest -q
npm run typecheck
npm run lint
npm run build
mkdir -p releases
task_commit="$(git rev-parse --short HEAD)"
git archive --format=tar.gz --output="releases/chengguan-hr-${task_commit}.tar.gz" HEAD
printf 'Source release ready: releases/chengguan-hr-%s.tar.gz\n' "$task_commit"
printf 'Run npm run demo:production on the target LM Studio host after installing dependencies.\n'
