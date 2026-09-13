#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
npm ci
uv run python -m backend.hr.seed
uv run ruff check backend tests scripts
uv run pytest -q
uv run python scripts/document_semantics.py --check
uv run python scripts/evaluate_semantics.py
npm run typecheck
npm run lint
npm run build
bash scripts/ci-smoke.sh
