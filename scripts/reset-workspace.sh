#!/usr/bin/env bash
# Wipe Me-Mex dev workspace: Mongo graph/dock data, session checkpoints (chat/jobs),
# trace logs — then seed a single global project with genesis node only.
#
# Usage (from repo root):
#   ./scripts/reset-workspace.sh              # interactive confirm
#   ./scripts/reset-workspace.sh -y            # non-interactive full wipe + seed
#   ./scripts/reset-workspace.sh -y --test-db  # pytest DB (test-me-mex)
#   ./scripts/reset-workspace.sh -y --keep-logs # skip llm_traces + decision_traces
#   ./scripts/reset-workspace.sh -y --collections-only # deleteMany on known cols only (no dropDatabase)
#
# Reads MONGO_URI and DB_NAME from backend/.env when present (see backend/.env.example).
# Always restart backend and voice_worker after a reset (in-memory job registry).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
DB_NAME="${DB_NAME:-me-mex}"
YES=0
USE_TEST_DB=0
KEEP_LOGS=0
COLLECTIONS_ONLY=0

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

log() { printf '[reset-workspace] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
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
    --test-db) USE_TEST_DB=1 ;;
    --keep-logs) KEEP_LOGS=1 ;;
    --collections-only) COLLECTIONS_ONLY=1 ;;
    --drop-db) log "Note: --drop-db is the default; flag is ignored." ;;
    --checkpoints | --traces | --all) log "Note: checkpoints and traces are cleared by default." ;;
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
if [[ "${COLLECTIONS_ONLY}" -eq 1 ]]; then
  log "Mongo: deleteMany on ${COLLECTIONS[*]}"
else
  log "Mongo: dropDatabase (empty DB, then seed global + genesis only)"
fi
log "Session: clear JSON checkpoints (transcript, jobs, scope drafts)"
if [[ "${KEEP_LOGS}" -eq 1 ]]; then
  log "Logs: keeping llm_traces and decision_traces (--keep-logs)"
else
  log "Logs: clear llm_traces and decision_traces"
fi

if [[ "${YES}" -ne 1 ]]; then
  read -r -p "Wipe workspace and reseed global? [y/N] " ans
  case "${ans}" in
    y | Y | yes | YES) ;;
    *) log "Aborted."; exit 0 ;;
  esac
fi

if [[ "${COLLECTIONS_ONLY}" -eq 1 ]]; then
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
else
  mongosh --quiet "${MONGO_URI}/${DB_NAME}" --eval 'db.dropDatabase()'
  log "Dropped database \"${DB_NAME}\"."
fi

ckpt_dir="${ROOT}/${CHECKPOINTS_DIR:-backend/data/checkpoints}"
if [[ -d "${ckpt_dir}" ]]; then
  find "${ckpt_dir}" -mindepth 1 -delete 2>/dev/null || true
  log "Cleared session checkpoints under ${ckpt_dir}."
else
  mkdir -p "${ckpt_dir}"
  log "Created empty checkpoint dir ${ckpt_dir}."
fi

if [[ "${KEEP_LOGS}" -eq 0 ]]; then
  trace_dir="${ROOT}/${DECISION_TRACE_DIR:-backend/logs/decision_traces}"
  if [[ -d "${trace_dir}" ]]; then
    find "${trace_dir}" -type f -name '*.jsonl' -delete 2>/dev/null || true
    log "Cleared decision traces under ${trace_dir}."
  fi

  llm_dir="${ROOT}/backend/logs/llm_traces"
  if [[ -d "${llm_dir}" ]]; then
    rm -f "${llm_dir}/index.jsonl"
    rm -rf "${llm_dir}/runs"
    mkdir -p "${llm_dir}/runs"
    log "Cleared LLM trace runs under ${llm_dir}."
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

log "Seeding global project (empty scope, genesis node only)..."
seed_global_project

log "Done."
log "Restart backend and voice_worker so in-memory jobs and stale briefing state are gone."
