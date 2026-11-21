#!/usr/bin/env bash
# Reset Me-Mex MongoDB (and optional local session files) for dev / e2e debugging.
#
# Usage (from repo root):
#   ./scripts/reset-mongo.sh              # interactive confirm, clear v2 collections, seed global project
#   ./scripts/reset-mongo.sh -y           # same, no prompt (+ global genesis workspace)
#   ./scripts/reset-mongo.sh --drop-db -y # drop entire DB_NAME database
#   ./scripts/reset-mongo.sh -y --checkpoints --traces
#   ./scripts/reset-mongo.sh -y --test-db # use test-me-mex (pytest default)
#
# Reads MONGO_URI and DB_NAME from backend/.env when present (see backend/.env.example).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
DB_NAME="${DB_NAME:-me-mex}"
DROP_DB=0
YES=0
USE_TEST_DB=0
CLEAR_CHECKPOINTS=0
CLEAR_TRACES=0

COLLECTIONS=(
  nodes
  edges
  projects
  passages
  documents
  staging
  pending_approvals
  highlights
  reorg_proposals
)

log() { printf '[reset-mongo] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

load_backend_env() {
  local env_file="${ROOT}/backend/.env"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
  MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
  DB_NAME="${DB_NAME:-me-mex}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help) usage ;;
    -y | --yes) YES=1 ;;
    --drop-db) DROP_DB=1 ;;
    --test-db) USE_TEST_DB=1 ;;
    --checkpoints) CLEAR_CHECKPOINTS=1 ;;
    --traces) CLEAR_TRACES=1 ;;
    --all)
      CLEAR_CHECKPOINTS=1
      CLEAR_TRACES=1
      ;;
    *)
      die "Unknown option: $1 (try --help)"
      ;;
  esac
  shift
done

load_backend_env
if [[ "${USE_TEST_DB}" -eq 1 ]]; then
  DB_NAME="test-me-mex"
fi

if [[ -z "${DB_NAME}" || "${DB_NAME}" == "admin" || "${DB_NAME}" == "local" ]]; then
  die "Refusing unsafe DB_NAME=${DB_NAME:-<empty>}"
fi

if ! command -v mongosh >/dev/null 2>&1; then
  die "mongosh not found — install MongoDB shell or use Docker: docker run --rm -it mongo mongosh ..."
fi

if ! mongosh --quiet "${MONGO_URI}" --eval 'db.runCommand({ ping: 1 })' >/dev/null 2>&1; then
  die "MongoDB not reachable at ${MONGO_URI}"
fi

log "Target: ${MONGO_URI} / database \"${DB_NAME}\""

if [[ "${DROP_DB}" -eq 1 ]]; then
  log "Mode: drop entire database"
else
  log "Mode: deleteMany on collections: ${COLLECTIONS[*]}"
fi

if [[ "${CLEAR_CHECKPOINTS}" -eq 1 ]]; then
  log "Also: clear LangGraph JSON checkpoints under ${CHECKPOINTS_DIR:-backend/data/checkpoints}"
fi
if [[ "${CLEAR_TRACES}" -eq 1 ]]; then
  log "Also: clear decision trace JSONL under ${DECISION_TRACE_DIR:-backend/logs/decision_traces}"
fi

if [[ "${YES}" -ne 1 ]]; then
  read -r -p "Continue? [y/N] " ans
  case "${ans}" in
    y | Y | yes | YES) ;;
    *) log "Aborted."; exit 0 ;;
  esac
fi

if [[ "${DROP_DB}" -eq 1 ]]; then
  mongosh --quiet "${MONGO_URI}/${DB_NAME}" --eval 'db.dropDatabase()'
  log "Dropped database \"${DB_NAME}\"."
else
  cols_list=""
  for c in "${COLLECTIONS[@]}"; do
  cols_list+="'${c}',"
  done
  cols_list="${cols_list%,}"
  mongosh --quiet "${MONGO_URI}/${DB_NAME}" --eval "
    const cols = [${cols_list}];
    for (const c of cols) {
      const r = db.getCollection(c).deleteMany({});
      print(c + ': deleted ' + r.deletedCount);
    }
  "
  log "Cleared collections in \"${DB_NAME}\"."
fi

if [[ "${CLEAR_CHECKPOINTS}" -eq 1 ]]; then
  ckpt_dir="${ROOT}/${CHECKPOINTS_DIR:-backend/data/checkpoints}"
  if [[ -d "${ckpt_dir}" ]]; then
    find "${ckpt_dir}" -type f -name '*.json' -delete 2>/dev/null || true
    log "Removed checkpoint JSON under ${ckpt_dir}."
  else
    log "No checkpoint dir at ${ckpt_dir} (skipped)."
  fi
fi

if [[ "${CLEAR_TRACES}" -eq 1 ]]; then
  trace_dir="${ROOT}/${DECISION_TRACE_DIR:-backend/logs/decision_traces}"
  if [[ -d "${trace_dir}" ]]; then
    find "${trace_dir}" -type f -name '*.jsonl' -delete 2>/dev/null || true
    log "Removed *.jsonl under ${trace_dir}."
  else
    log "No trace dir at ${trace_dir} (skipped)."
  fi
fi

seed_global_project() {
  local py=""
  if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
    py="${ROOT}/backend/.venv/bin/python"
  elif command -v poetry >/dev/null 2>&1 && [[ -f "${ROOT}/backend/pyproject.toml" ]]; then
    (cd "${ROOT}/backend" && poetry run python "${ROOT}/scripts/seed-global-project.py")
    return
  else
    py="python3"
  fi
  PYTHONPATH="${ROOT}/backend" MONGO_URI="${MONGO_URI}" DB_NAME="${DB_NAME}" \
    "${py}" "${ROOT}/scripts/seed-global-project.py"
}

log "Seeding default global project (genesis node, empty scope)..."
seed_global_project

log "Done. Restart backend/voice_worker if they cache store state in-process."
