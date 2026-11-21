#!/usr/bin/env bash
# Deprecated wrapper — use reset-workspace.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
printf '[reset-mongo] This script was renamed to reset-workspace.sh — forwarding arguments.\n' >&2
exec "${ROOT}/scripts/reset-workspace.sh" "$@"
