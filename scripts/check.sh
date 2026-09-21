#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check backend tests scripts integrations
uv run pytest -q
uv run python scripts/document_catalog.py --check
npm run typecheck
npm run lint
npm run build
bash scripts/ci-smoke.sh
