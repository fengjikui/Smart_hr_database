#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
npm ci
uv run python -m backend.hr.seed
uv run ruff check backend tests scripts
uv run pytest -q
npm run typecheck
npm run lint
npm run build
