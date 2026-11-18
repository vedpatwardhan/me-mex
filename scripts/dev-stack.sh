#!/usr/bin/env bash
# Spin up Me-Mex local voice stack: LiveKit SFU, agent worker, FastAPI, Vite frontend.
# MongoDB is NOT started here — use your existing local instance (e.g. brew services).
#
# Usage:
#   ./scripts/dev-stack.sh          # start (foreground; Ctrl+C stops all)
#   ./scripts/dev-stack.sh stop     # stop without starting
#   ./scripts/dev-stack.sh restart  # stop then start
#
# Prerequisites: docker, uv, node/npm, backend/.env (COLAB_INFERENCE_BASE_URL, MONGO_URI).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT}/.dev-stack"
LOG_DIR="${STATE_DIR}/logs"
PID_FILE="${STATE_DIR}/pids.env"
LIVEKIT_CONTAINER="${LIVEKIT_CONTAINER:-me-mex-livekit}"

LIVEKIT_HTTP_PORT="${LIVEKIT_HTTP_PORT:-7880}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

mkdir -p "${LOG_DIR}"

log() { printf '[dev-stack] %s\n' "$*"; }

load_backend_env() {
  local env_file="${ROOT}/backend/.env"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  else
    log "WARN: ${env_file} missing — copy from backend/.env.example"
  fi
}

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    nc -z 127.0.0.1 "${port}" >/dev/null 2>&1
  fi
}

kill_pidfile() {
  [[ -f "${PID_FILE}" ]] || return 0
  # shellcheck disable=SC1090
  source "${PID_FILE}"
  local key pid
  for key in backend agent frontend; do
    pid="${!key:-}"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      log "Stopping ${key} (pid ${pid})"
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
    fi
  done
  rm -f "${PID_FILE}"
}

stop_livekit_docker() {
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "${LIVEKIT_CONTAINER}"; then
    log "Stopping LiveKit container ${LIVEKIT_CONTAINER}"
    docker rm -f "${LIVEKIT_CONTAINER}" >/dev/null 2>&1 || true
  fi
}

warn_mongo_docker() {
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -Eiq 'mongo'; then
    log "WARN: A MongoDB *Docker* container is running. This stack expects local MongoDB only (no Docker)."
  fi
}

check_mongo() {
  if command -v mongosh >/dev/null 2>&1; then
    if ! mongosh --quiet "${MONGO_URI:-mongodb://localhost:27017}" --eval 'db.runCommand({ ping: 1 })' >/dev/null 2>&1; then
      log "WARN: MongoDB not reachable at ${MONGO_URI:-mongodb://localhost:27017} — start brew services / your existing DB"
    fi
  fi
}

start_livekit_docker() {
  if port_in_use "${LIVEKIT_HTTP_PORT}"; then
    log "Port ${LIVEKIT_HTTP_PORT} already in use — assuming LiveKit SFU is running"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    log "ERROR: docker not found; required for LiveKit SFU"
    exit 1
  fi
  stop_livekit_docker
  log "Starting LiveKit SFU (docker) on ws://localhost:${LIVEKIT_HTTP_PORT}"
  docker run -d --name "${LIVEKIT_CONTAINER}" \
    -p "${LIVEKIT_HTTP_PORT}:7880" -p 7881:7881 -p 7882:7882/udp \
    -e LIVEKIT_KEYS="devkey: secret" \
    livekit/livekit-server --dev >/dev/null

  local i
  for i in $(seq 1 30); do
    if port_in_use "${LIVEKIT_HTTP_PORT}"; then
      return 0
    fi
    sleep 0.5
  done
  log "ERROR: LiveKit did not bind port ${LIVEKIT_HTTP_PORT} in time (see: docker logs ${LIVEKIT_CONTAINER})"
  exit 1
}

start_backend() {
  if port_in_use "${BACKEND_PORT}"; then
    log "ERROR: port ${BACKEND_PORT} in use — run: ./scripts/dev-stack.sh stop"
    exit 1
  fi
  (
    cd "${ROOT}"
    export CHAT_LLM_MODE="${CHAT_LLM_MODE:-live}"
    export DECISION_SCORER_MODE="${DECISION_SCORER_MODE:-live}"
    exec uv run uvicorn main:app --app-dir backend --host 127.0.0.1 --port "${BACKEND_PORT}" --reload
  ) >>"${LOG_DIR}/backend.log" 2>&1 &
  echo "backend=$!" >"${PID_FILE}"
  log "Backend http://127.0.0.1:${BACKEND_PORT} (log: ${LOG_DIR}/backend.log)"
}

start_agent() {
  load_backend_env
  export ME_MEX_BACKEND_URL="${ME_MEX_BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"
  export LIVEKIT_URL="${LIVEKIT_URL:-ws://127.0.0.1:${LIVEKIT_HTTP_PORT}}"
  export LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-devkey}"
  export LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-secret}"
  if [[ -z "${COLAB_INFERENCE_BASE_URL:-}" ]]; then
    log "WARN: COLAB_INFERENCE_BASE_URL unset — voice STT/TTS will fail until Colab gateway is reachable"
  fi
  (
    cd "${ROOT}/agent"
    uv sync --quiet 2>/dev/null || uv sync
    exec uv run python -m me_mex_agent.worker dev
  ) >>"${LOG_DIR}/agent.log" 2>&1 &
  echo "agent=$!" >>"${PID_FILE}"
  log "LiveKit agent worker (log: ${LOG_DIR}/agent.log)"
}

start_frontend() {
  if port_in_use "${FRONTEND_PORT}"; then
    log "ERROR: port ${FRONTEND_PORT} in use — run: ./scripts/dev-stack.sh stop"
    exit 1
  fi
  if [[ ! -d "${ROOT}/frontend/node_modules" ]]; then
    log "Installing frontend npm deps…"
    (cd "${ROOT}/frontend" && npm install)
  fi
  (
    cd "${ROOT}/frontend"
    export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://127.0.0.1:${BACKEND_PORT}}"
    exec npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}"
  ) >>"${LOG_DIR}/frontend.log" 2>&1 &
  echo "frontend=$!" >>"${PID_FILE}"
  log "Frontend http://127.0.0.1:${FRONTEND_PORT} (log: ${LOG_DIR}/frontend.log)"
}

wait_for_backend() {
  local i
  for i in $(seq 1 40); do
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  log "WARN: backend health check timed out — see ${LOG_DIR}/backend.log"
}

shutdown_all() {
  log "Shutting down…"
  kill_pidfile
  stop_livekit_docker
}

cmd_stop() {
  kill_pidfile
  stop_livekit_docker
  log "Stopped."
}

cmd_start() {
  warn_mongo_docker
  load_backend_env
  check_mongo
  kill_pidfile
  stop_livekit_docker

  start_livekit_docker
  start_backend
  wait_for_backend
  start_agent
  start_frontend

  trap shutdown_all INT TERM

  log ""
  log "Ready for voice E2E:"
  log "  App:     http://127.0.0.1:${FRONTEND_PORT}"
  log "  API:     http://127.0.0.1:${BACKEND_PORT}/docs"
  log "  LiveKit: ${LIVEKIT_URL:-ws://localhost:${LIVEKIT_HTTP_PORT}}"
  log ""
  log "Tail logs: tail -f ${LOG_DIR}/*.log"
  log "Press Ctrl+C to stop all services."

  wait
}

main() {
  local cmd="${1:-start}"
  case "${cmd}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_stop; cmd_start ;;
    -h | --help)
      sed -n '2,9p' "$0"
      ;;
    *)
      log "Unknown command: ${cmd} (use start | stop | restart)"
      exit 1
      ;;
  esac
}

main "$@"
