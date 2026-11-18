# Colab inference — operator runbook

Bring up **remote inference** for Me-Mex v2 on a Colab GPU VM: **Ministral chat (vLLM)**, **BGE cross-encoder decision routing**, and (optional) **speech** — all behind **one HTTPS URL**.

**See also:** [TOPOLOGY.md](./TOPOLOGY.md) · [me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb) · [docs/05-models-and-runtime.md](../docs/05-models-and-runtime.md)

---

## 1. What runs where

| Capability | Colab process | Path (via tunnel) | Local env |
|------------|---------------|-------------------|-----------|
| **Chat / tools** | vLLM `:8000` (GPU) | `POST …/v1/chat/completions` | `COLAB_INFERENCE_BASE_URL`, `CHAT_LLM_MODE=live` |
| **Decision routing** | Gateway CPU (cross-encoder) | `POST …/v1/decision/score` | `DECISION_SCORER_MODE=live` |
| **STT / TTS** (Phase 2) | `speech_sidecar` `:7861` | `POST …/stt/*`, `…/tts/*` | same `COLAB_INFERENCE_BASE_URL` |

**Public entrypoint:** `inference_gateway` on **`:7860`**. Point cloudflared here — not at vLLM `:8000`.

**Reranker:** `BGE_RERANKER_MODEL` (default `BAAI/bge-reranker-base`) loads in the gateway process on CPU. First `/health` or `/v1/decision/score` may download weights from Hugging Face.

---

## 2. Prerequisites

**Colab:** GPU runtime (T4/L4); Hugging Face login for Ministral (notebook §2); `colab/` files on the VM (`inference_gateway.py`, `reranker_service.py`, `scoring_text.py`, `speech_sidecar.py`, `requirements-colab.txt`).

**Mac:** `uv sync`; `backend/.env` from [`.env.example`](../backend/.env.example). Mongo only if you run full pytest/e2e — not required for gateway smoke alone.

### 2.1 Pip install (Colab)

From `colab/` on the VM:

```bash
cd /content/me-mex/colab   # or your clone path

# Core: vLLM + gateway reranker
pip install -q -r requirements-colab.txt
pip uninstall -y torchaudio 2>/dev/null || true

# Speech (Phase 2): Whisper STT + edge-tts (ffmpeg for mp3→wav)
apt-get -qq -y install ffmpeg
pip install -q -r requirements-colab-speech.txt
```

`curl -s http://127.0.0.1:7861/health` should show `"tts":"edge"`.

Chat-only bring-up skips the speech block; gateway `/stt` `/tts` proxy will 502 until sidecar deps are installed.

---

## 3. Colab bring-up — processes, not “two commands”

On Colab you need **several long-running processes** on the same VM. They are **not** one notebook cell that blocks forever, and the public URL must **not** point at vLLM directly.

### 3.1 What actually runs (Phase 1 minimum = 3 processes)

| # | Process | Port | Role |
|---|---------|------|------|
| **1** | **vLLM** | `8000` (localhost) | Ministral **chat** on GPU |
| **2** | **inference_gateway** | `7860` | Proxies `/v1/chat/*` → vLLM; serves `/v1/decision/score` (**BGE reranker** loads inside this process on CPU); proxies `/stt/*` `/tts/*` → speech when enabled |
| **3** | **cloudflared** | HTTPS | Tunnel from internet → **`7860` only** |

**Phase 2 add a 4th process** (still one tunnel):

| # | Process | Port | Role |
|---|---------|------|------|
| **4** | **speech_sidecar** | `7861` (localhost) | Whisper + edge-tts on CPU |

“Four models” in the product spec = **chat (vLLM) + reranker (in gateway) + STT + TTS** — but **reranker is not a separate daemon**; only vLLM, gateway, speech (optional), and cloudflared are separate processes.

```text
Internet ──cloudflared──► gateway :7860 ──┬── proxy ──► vLLM :8000 (GPU)
                                         ├── BGE reranker (in-process CPU)
                                         └── proxy ──► speech :7861 (optional)
```

**Blocking rule:** `vllm serve` and `uvicorn` **block the shell** in the foreground. Use **tmux windows**, **notebook background** (`&` / `Popen`), or **`tee` to log files** — Colab gives you **one** embedded terminal, not multiple tabs.

### 3.2 Canonical commands (copy-paste)

Run from **`colab/`** on the Colab VM after §2 deps + HF login. **Order:** (1) vLLM → wait for `/v1/models` → (2) speech optional → (2b) gateway → (3) cloudflared.

Append `2>&1 | tee -a logs/<name>.log` (see §3.3). Or use **§3.4** tmux/script to run the same commands.

#### (1) vLLM — chat on GPU (`:8000`)

Colab notebook cell (blocks unless you use tmux or suffix `&` + log redirect):

```bash
vllm serve mistralai/Ministral-3-8B-Reasoning-2512 \
    --host 127.0.0.1 \
    --port 8000 \
    --tokenizer-mode mistral \
    --config-format mistral \
    --load-format mistral \
    --enable-auto-tool-choice \
    --tool-call-parser mistral \
    --reasoning-parser mistral \
    --max-model-len 12288 \
    --max-num-seqs 8 \
    --max-num-batched-tokens 8192 \
    --gpu-memory-utilization 0.95 \
    --enable-prefix-caching
```

In a **notebook** code cell, prefix with `!` on the first line only, or paste into a **tmux** `vllm` window.

Ready check (another cell or shell):

```bash
curl -s http://127.0.0.1:8000/v1/models
```

Set Mac/backend `LLM_MODEL_NAME=mistralai/Ministral-3-8B-Reasoning-2512` to match.

#### (2a) Speech sidecar — optional Phase 1, required Phase 2 (`:7861`)

```bash
cd /content/me-mex/colab
uvicorn speech_sidecar:app --host 127.0.0.1 --port 7861
```

#### (2b) Inference gateway — public HTTP surface + reranker (`:7860`)

Start **after** vLLM is healthy. Proxies chat to `:8000`; serves `/v1/decision/score` on CPU.

```bash
cd /content/me-mex/colab
export VLLM_BASE=http://127.0.0.1:8000/v1
export SPEECH_BASE=http://127.0.0.1:7861
export BGE_RERANKER_MODEL=BAAI/bge-reranker-base
export LLM_MODEL_NAME=mistralai/Ministral-3-8B-Reasoning-2512
uvicorn inference_gateway:app --host 0.0.0.0 --port 7860
```

Ready check:

```bash
curl -s http://127.0.0.1:7860/health
```

#### (3) cloudflared — tunnel to **gateway**, not vLLM

v1 tunneled **`127.0.0.1:8000`** (vLLM only). v2 tunnels **`127.0.0.1:7860`** (gateway) so chat, `/v1/decision/score`, and speech share one hostname.

```bash
cd /content/me-mex/colab
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
./cloudflared tunnel --url http://127.0.0.1:7860 --http-host-header "127.0.0.1:7860"
```

Copy the printed `https://….trycloudflare.com` URL → Mac:

`COLAB_INFERENCE_BASE_URL=https://….trycloudflare.com`

Optional: [notebook §8](me_mex_inference_stack.ipynb) installs the binary under `/usr/local/bin/cloudflared`; either path is fine.

### 3.3 Log files (all bring-up paths)

Every long-running process should append to **`colab/logs/`** on the Colab VM (not committed to git). Use **`tee -a`** so you still see output in tmux or notebook while persisting for later debugging.

| Log file | Process | Typical contents |
|----------|---------|------------------|
| `logs/vllm.log` | vLLM `:8000` | Model load, OOM, request errors |
| `logs/gateway.log` | `inference_gateway` `:7860` | Uvicorn access log, reranker load, proxy errors to vLLM/speech |
| `logs/speech.log` | `speech_sidecar` `:7861` | Whisper / edge-tts (Phase 2) |
| `logs/cloudflared.log` | cloudflared | **Public HTTPS URL** (`trycloudflare.com`), tunnel errors |

Create the directory once per session:

```bash
cd /content/me-mex/colab   # your COLAB_DIR
mkdir -p logs
```

**Pattern** (use in tmux or notebook `!` cells):

```bash
some_long_running_command 2>&1 | tee -a logs/<name>.log
```

**Follow logs** from a notebook cell or the tmux `logs` window. Create empty placeholders first so `tail -F` does not error while gateway/tunnel have not started yet (`gateway.log` / `cloudflared.log` appear only after their `sleep` windows):

```bash
touch logs/vllm.log logs/gateway.log logs/speech.log logs/cloudflared.log
tail -F logs/vllm.log logs/gateway.log logs/speech.log logs/cloudflared.log
```

Download for offline debugging: Colab **Files** pane → `colab/logs/` → right-click → download. When reporting issues, attach the relevant `.log` snippets (startup through first error).

### 3.4 Recommended: **tmux** (one Colab terminal, five windows)

Colab does **not** provide multiple terminal tabs. Use **tmux** so each process has its own window and **tee** writes `logs/*.log`.

Session name: **`me-mex-inference`**

| Window | Starts | Log file |
|--------|--------|----------|
| `vllm` | vLLM on `:8000` | `logs/vllm.log` |
| `speech` | speech sidecar `:7861` | `logs/speech.log` |
| `gateway` | after ~90s, gateway `:7860` | `logs/gateway.log` |
| `tunnel` | after ~120s, cloudflared → `:7860` | `logs/cloudflared.log` |
| `logs` | `tail -F` on all four logs | — |

#### 3.4a Fast path — helper script

```bash
apt-get update -qq && apt-get install -y -qq tmux
unset TMUX
cd /content/me-mex/colab
chmod +x start_inference_tmux.sh
./start_inference_tmux.sh reasoning
tmux attach -t me-mex-inference
```

Same as [start_inference_tmux.sh](./start_inference_tmux.sh) (optional `./start_inference_tmux.sh instruct` for Instruct weights).

#### 3.4b Spin up tmux — full command block (no script)

Paste into **one** Colab terminal or a notebook `%%bash` cell. Set `COLAB_DIR` if your repo is not under `/content/me-mex/colab`.

```bash
set -e
COLAB_DIR=/content/me-mex/colab
SESSION=me-mex-inference

apt-get update -qq && apt-get install -y -qq tmux
cd "$COLAB_DIR"
mkdir -p logs
touch logs/vllm.log logs/gateway.log logs/speech.log logs/cloudflared.log
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Window: vllm
tmux new-session -d -s "$SESSION" -n vllm
tmux send-keys -t "${SESSION}:vllm" \
  "cd ${COLAB_DIR} && vllm serve mistralai/Ministral-3-8B-Reasoning-2512 \
    --host 127.0.0.1 --port 8000 \
    --tokenizer-mode mistral --config-format mistral --load-format mistral \
    --enable-auto-tool-choice --tool-call-parser mistral --reasoning-parser mistral \
    --max-model-len 12288 --max-num-seqs 8 --max-num-batched-tokens 8192 \
    --gpu-memory-utilization 0.95 --enable-prefix-caching \
    2>&1 | tee -a logs/vllm.log" C-m

# Window: speech
tmux new-window -t "$SESSION" -n speech
tmux send-keys -t "${SESSION}:speech" \
  "cd ${COLAB_DIR} && uvicorn speech_sidecar:app --host 127.0.0.1 --port 7861 \
    2>&1 | tee -a logs/speech.log" C-m

# Window: gateway (waits for vLLM load)
tmux new-window -t "$SESSION" -n gateway
tmux send-keys -t "${SESSION}:gateway" \
  "sleep 90 && cd ${COLAB_DIR} && \
    export VLLM_BASE=http://127.0.0.1:8000/v1 SPEECH_BASE=http://127.0.0.1:7861 \
    BGE_RERANKER_MODEL=BAAI/bge-reranker-base \
    LLM_MODEL_NAME=mistralai/Ministral-3-8B-Reasoning-2512 && \
    uvicorn inference_gateway:app --host 0.0.0.0 --port 7860 \
    2>&1 | tee -a logs/gateway.log" C-m

# Window: tunnel (waits for gateway)
tmux new-window -t "$SESSION" -n tunnel
tmux send-keys -t "${SESSION}:tunnel" \
  "sleep 120 && cd ${COLAB_DIR} && \
    (test -x ./cloudflared || (curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared && chmod +x cloudflared)) && \
    ./cloudflared tunnel --url http://127.0.0.1:7860 --http-host-header \"127.0.0.1:7860\" \
    2>&1 | tee -a logs/cloudflared.log" C-m

# Window: tail logs
tmux new-window -t "$SESSION" -n logs
tmux send-keys -t "${SESSION}:logs" \
  "cd ${COLAB_DIR} && tail -F logs/vllm.log logs/gateway.log logs/speech.log logs/cloudflared.log" C-m

tmux attach -t "$SESSION"
```

After detach (`Ctrl-b` then `d`), re-attach anytime:

```bash
tmux attach -t me-mex-inference
```

Copy the tunnel URL from the **`tunnel`** window or `logs/cloudflared.log` → Mac `COLAB_INFERENCE_BASE_URL=…` (§4).

#### 3.4c Spin up tmux — interactive (five windows by hand)

Use this if you want to start **gateway** only after `curl -s http://127.0.0.1:8000/v1/models` succeeds (skip fixed `sleep`).

```bash
apt-get update -qq && apt-get install -y -qq tmux
cd /content/me-mex/colab && mkdir -p logs
touch logs/vllm.log logs/gateway.log logs/speech.log logs/cloudflared.log
tmux new -s me-mex-inference
```

Inside tmux:

1. **Window 0** — paste **§3.2 (1) vLLM** and append: `2>&1 | tee -a logs/vllm.log`. Wait until models load (or run `curl` from another Colab cell).
2. `Ctrl-b` `c` — new window; `Ctrl-b` `,` → rename to `speech`. Run **§3.2 (2a)** + `2>&1 | tee -a logs/speech.log`.
3. `Ctrl-b` `c` → rename `gateway`. Run **§3.2 (2b)** + `2>&1 | tee -a logs/gateway.log`.
4. `Ctrl-b` `c` → rename `tunnel`. Run **§3.2 (3)** + `2>&1 | tee -a logs/cloudflared.log`.
5. `Ctrl-b` `c` → rename `logs`. Run §3.3 `touch` + `tail -F` (or `tail -F` only if all four files already exist).

#### 3.4d tmux controls (Colab terminal)

| Keys | Action |
|------|--------|
| `Ctrl-b` `d` | Detach (servers keep running) |
| `tmux attach -t me-mex-inference` | Re-attach |
| `Ctrl-b` `w` | Pick window by name |
| `Ctrl-b` `n` / `p` | Next / previous window |
| `Ctrl-b` `|` | Split pane (optional) |
| `tmux kill-session -t me-mex-inference` | Stop all windows in session |

### 3.5 Alternative: notebook cells (background + logs)

Open **[me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb)**. Prefer adding **`tee -a logs/…`** to each background start (the stock notebook uses `Popen` / `&` without files — fine for smoke, weak for debugging).

| Order | Section | What happens |
|-------|---------|----------------|
| §0–§2 | Setup | `mkdir -p logs`, deps, HF login |
| §5 | vLLM | `vllm … &` + wait loop → also redirect: `… 2>&1 \| tee -a logs/vllm.log &` |
| §6 | Speech | sidecar → `logs/speech.log` |
| §7 | Gateway | after vLLM ready → `logs/gateway.log` |
| §8 | Tunnel | cloudflared → `logs/cloudflared.log` (URL appears here) |
| §9 | Smoke | Public HTTP checks |

For day-to-day ops with readable history, **§3.4 tmux** is usually easier than editing notebook `Popen` calls.

### 3.6 What not to do

- Point cloudflared at vLLM **`:8000`** instead of gateway **`:7860`**.
- Run `vllm serve` in a **blocking** notebook cell with no `&` and no tmux window.
- Start **gateway** before vLLM responds on `/v1/models`.
- Rely on notebook output alone with no **`logs/`** files when something fails mid-session.

Paste the tunnel hostname into local config (§4).

---

## 4. Local `.env`

```env
COLAB_INFERENCE_BASE_URL=https://YOUR_SUBDOMAIN.trycloudflare.com
CHAT_LLM_MODE=live
DECISION_SCORER_MODE=live
LLM_MODEL_NAME=mistralai/Ministral-3-8B-Reasoning-2512
LLM_TIMEOUT=180
```

Set **only the tunnel origin** (no `/v1`). The backend appends paths:

- `{base}/v1/chat/completions`, `{base}/v1/decision/score`
- `{base}/stt/*`, `{base}/tts/*` (Phase 2 voice)

`LLM_MODEL_NAME` must match the weights vLLM is serving.

---

## 5. Verification

### Health

```bash
curl -sS "https://YOUR_SUBDOMAIN.trycloudflare.com/health"
```

Expect `status`, `vllm`, `reranker_model`.

### Decision `/v1/decision/score`

```bash
curl -sS -X POST "https://YOUR_SUBDOMAIN.trycloudflare.com/v1/decision/score" \
  -H "Content-Type: application/json" \
  -d '{
    "query_node": {"id": "q", "title": "query", "node_kind": "ROOT"},
    "frontier": [
      {"id": "a", "title": "A", "node_kind": "CONCEPT_M"},
      {"id": "b", "title": "B", "node_kind": "CONCEPT_M"}
    ]
  }'
```

Expect `relevance_probs` with keys `a` and `b`, probabilities summing ≈ 1.

### Speech (Phase 2) — STT / TTS via same tunnel host

```bash
# TTS smoke
curl -sS -X POST "https://YOUR_SUBDOMAIN.trycloudflare.com/tts/synthesize" \
  -H "Content-Type: application/json" \
  -d '{"text":"Me-Mex speech smoke test.","voice":"af"}' \
  -o /tmp/me-mex-tts.wav && file /tmp/me-mex-tts.wav
```

STT: `POST …/stt/transcribe` with multipart field `audio` (short `.wav`).

If `speech.log` shows `TypeError: open() got an unexpected keyword argument 'metadata_errors'`, upgrade PyAV and restart the sidecar:

```bash
pip install -U 'av>=12.0.0'
# restart uvicorn speech_sidecar on :7861
```

### Backend (Mac)

```bash
cd me-mex/backend
DECISION_SCORER_MODE=live uv run pytest tests/integration/decision -m vllm -v
```

Marker `vllm` = live **inference gateway** (chat proxy + reranker). Phase 1 ops gate per [docs/11-testing.md](../docs/11-testing.md).

### Chat (optional)

`CHAT_LLM_MODE=live` and `POST /api/agent/turn`, or call `llm_gateway` directly.

---

## 6. Optional — reranker quality eval (local)

**Not part of Colab bring-up.** After the tunnel works, you can score held-out bootstrap rows on your Mac:

```bash
cd me-mex/backend
# Generate val.jsonl if needed — see backend/data/decision_training/README.md
DECISION_SCORER_MODE=live uv run python scripts/eval_decision_model.py \
  --val data/decision_training/robotics/val.jsonl --live \
  --out data/decision_training/eval_report.json
```

Optional thresholds: `data/decision_training/eval_gate.json`.

---

## 7. Phase 1 ops checklist

- [ ] vLLM healthy on Colab `8000`
- [ ] Gateway `/health` shows reranker model
- [ ] Tunnel URL in `COLAB_INFERENCE_BASE_URL` (no `/v1` suffix)
- [ ] `pytest -m vllm` (decision integration) green
- [ ] (Optional) `eval_decision_model.py --live` + saved report
- [ ] (Optional) full `uv run pytest` with Mongo

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| 404 on `/v1/decision/score` | Tunnel must target gateway **`:7860`**, not vLLM `:8000` |
| Decision fails, chat works | Set `COLAB_INFERENCE_BASE_URL` to gateway host (backend adds `/v1`) |
| vLLM OOM | Lower `--max-model-len`, reduce `--gpu-memory-utilization`, or FP8 weights |
| Slow first decision | BGE download; warm with `/health` |
| Uniform probs + `warning` in JSON | Read `logs/gateway.log`; HF access; Colab CPU RAM |
| Empty notebook output but failures on Mac | Inspect `colab/logs/*.log` on the VM |
| Tunnel broke | New Colab session → new URL → update `.env` |

---

## 9. Files in `colab/`

| File | Purpose |
|------|---------|
| [me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb) | Operator notebook |
| [inference_gateway.py](./inference_gateway.py) | vLLM proxy, `/v1/decision/score`, speech proxy |
| [reranker_service.py](./reranker_service.py) | Cross-encoder scoring |
| [scoring_text.py](./scoring_text.py) | Pair text formatting |
| [speech_sidecar.py](./speech_sidecar.py) | Whisper + edge-tts |
| [requirements-colab.txt](./requirements-colab.txt) | Core pip pins (vLLM, gateway) |
| [requirements-colab-speech.txt](./requirements-colab-speech.txt) | Speech sidecar pip pins |
| [TOPOLOGY.md](./TOPOLOGY.md) | Architecture diagram |
| [start_inference_tmux.sh](./start_inference_tmux.sh) | tmux session + `logs/*.log` via `tee` |
| `logs/` | Runtime log directory on Colab (gitignored `*.log`) |

---

## 10. Phase 2 voice (local + Colab)

| Step | Where |
|------|--------|
| STT/TTS weights | Colab `speech_sidecar` + tunnel (`COLAB_INFERENCE_BASE_URL` on Mac) |
| WebRTC | Local LiveKit Docker `:7880` |
| Bridge | `agent/me_mex_agent/worker.py` (mic → STT → graph → TTS) |
| UI | Frontend `VoiceRail` + `RecommendationsDock` |

Same tunnel host as `COLAB_INFERENCE_BASE_URL`. LiveKit stays local. Notebook §10.
