#!/usr/bin/env bash
# Install git pre-commit hook (ruff format/check + basic file hygiène).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
uv sync --group dev
uv run pre-commit install --install-hooks
echo "Pre-commit hook installed at .git/hooks/pre-commit"
echo "Manual full-repo pass: uv run pre-commit run --all-files"
