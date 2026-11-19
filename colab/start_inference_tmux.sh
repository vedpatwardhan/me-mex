#!/usr/bin/env bash
# Start Me-Mex Colab inference processes in tmux windows; append stdout/stderr to logs/.
# Usage: ./start_inference_tmux.sh [instruct|reasoning]
# Attach: tmux attach -t me-mex-inference
set -euo pipefail

COLAB_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${COLAB_DIR}/logs"
SESSION="${TMUX_SESSION:-me-mex-inference}"
VLLM_VARIANT="${1:-reasoning}"

mkdir -p "$LOG_DIR"
touch "${LOG_DIR}/vllm.log" "${LOG_DIR}/speech.log" "${LOG_DIR}/gateway.log" "${LOG_DIR}/cloudflared.log"
echo "Logs: ${LOG_DIR}/"

if ! command -v tmux &>/dev/null; then
  echo "Installing tmux..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tmux
fi

if [[ "$VLLM_VARIANT" == "instruct" ]]; then
  VLLM_MODEL="mistralai/Ministral-3-8B-Instruct-2512"
  VLLM_LEN=8192
  VLLM_SEQS=4
  VLLM_BATCHED=""
  VLLM_EXTRA=""
  VLLM_UTIL=0.90
else
  VLLM_MODEL="mistralai/Ministral-3-8B-Reasoning-2512"
  VLLM_LEN=12288
  VLLM_SEQS=8
  VLLM_BATCHED="--max-num-batched-tokens 8192"
  VLLM_EXTRA="--reasoning-parser mistral"
  VLLM_UTIL=0.95
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Killing existing session: $SESSION"
  tmux kill-session -t "$SESSION"
fi

VLLM_CMD="cd ${COLAB_DIR} && vllm serve ${VLLM_MODEL} \
  --host 127.0.0.1 --port 8000 \
  --tokenizer-mode mistral --config-format mistral --load-format mistral \
  --enable-auto-tool-choice --tool-call-parser mistral ${VLLM_EXTRA} \
  --max-model-len ${VLLM_LEN} --max-num-seqs ${VLLM_SEQS} ${VLLM_BATCHED} \
  --gpu-memory-utilization ${VLLM_UTIL} \
  --enable-prefix-caching 2>&1 | tee -a ${LOG_DIR}/vllm.log"

SPEECH_CMD="cd ${COLAB_DIR} && export WHISPER_MODEL=\${WHISPER_MODEL:-base.en} WHISPER_DEVICE=\${WHISPER_DEVICE:-cpu} WHISPER_COMPUTE=\${WHISPER_COMPUTE:-int8} WHISPER_BEAM_SIZE=\${WHISPER_BEAM_SIZE:-5} && uvicorn speech_sidecar:app --host 127.0.0.1 --port 7861 \
  2>&1 | tee -a ${LOG_DIR}/speech.log"

GW_CMD="cd ${COLAB_DIR} && export VLLM_BASE=http://127.0.0.1:8000/v1 \
  SPEECH_BASE=http://127.0.0.1:7861 \
  BGE_RERANKER_MODEL=BAAI/bge-reranker-base \
  LLM_MODEL_NAME=${VLLM_MODEL} && \
  uvicorn inference_gateway:app --host 0.0.0.0 --port 7860 \
  2>&1 | tee -a ${LOG_DIR}/gateway.log"

CF_CMD="cd ${COLAB_DIR} && (test -x ./cloudflared || (curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared && chmod +x cloudflared)) && ./cloudflared tunnel --url http://127.0.0.1:7860 --http-host-header \"127.0.0.1:7860\" 2>&1 | tee -a ${LOG_DIR}/cloudflared.log"

tmux new-session -d -s "$SESSION" -n vllm
tmux send-keys -t "${SESSION}:vllm" "$VLLM_CMD" C-m

tmux new-window -t "$SESSION" -n speech
tmux send-keys -t "${SESSION}:speech" "$SPEECH_CMD" C-m

tmux new-window -t "$SESSION" -n gateway
tmux send-keys -t "${SESSION}:gateway" "sleep 90" C-m
tmux send-keys -t "${SESSION}:gateway" "$GW_CMD" C-m

tmux new-window -t "$SESSION" -n tunnel
tmux send-keys -t "${SESSION}:tunnel" "sleep 120" C-m
tmux send-keys -t "${SESSION}:tunnel" "$CF_CMD" C-m

tmux new-window -t "$SESSION" -n logs
tmux send-keys -t "${SESSION}:logs" "tail -F ${LOG_DIR}/vllm.log ${LOG_DIR}/gateway.log ${LOG_DIR}/speech.log ${LOG_DIR}/cloudflared.log" C-m

echo "Session $SESSION started. Attach: tmux attach -t $SESSION"
echo "Windows: vllm → speech → gateway (waits ~90s) → tunnel (waits ~120s) → logs (tail -F)"
echo "Copy tunnel URL from cloudflared.log or the tunnel window."
