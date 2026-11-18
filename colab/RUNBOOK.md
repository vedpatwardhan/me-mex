# Colab inference — operator runbook

Bring up **remote inference** for Me-Mex v2 on a Colab GPU VM: **Ministral chat (vLLM)**, **BGE cross-encoder decision routing**, and (optional) **speech** — all behind **one HTTPS URL**.

**See also:** [TOPOLOGY.md](./TOPOLOGY.md) · [me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb) · [docs/05-models-and-runtime.md](../docs/05-models-and-runtime.md)

---

## 1. What runs where

| Capability | Colab process | Path (via tunnel) | Local env |
|------------|---------------|-------------------|-----------|
| **Chat / tools** | vLLM `:8000` (GPU) | `POST …/v1/chat/completions` | `COLAB_VLLM_URL`, `CHAT_LLM_MODE=live` |
| **Decision routing** | Gateway CPU (cross-encoder) | `POST …/v1/decision/score` | `DECISION_SCORER_MODE=live` |
| **STT / TTS** (Phase 2) | `speech_sidecar` `:7861` | `POST …/stt/*`, `…/tts/*` | `COLAB_SPEECH_BASE_URL` (no `/v1`) |

**Public entrypoint:** `inference_gateway` on **`:7860`**. Point cloudflared here — not at vLLM `:8000`.

**Reranker:** `BGE_RERANKER_MODEL` (default `BAAI/bge-reranker-base`) loads in the gateway process on CPU. First `/health` or `/v1/decision/score` may download weights from Hugging Face.

---

## 2. Prerequisites

**Colab:** GPU runtime (T4/L4); Hugging Face login for Ministral (notebook §2); `colab/` files on the VM (`inference_gateway.py`, `reranker_service.py`, `scoring_text.py`, `speech_sidecar.py`, `requirements-colab.txt`).

**Mac:** `uv sync`; `backend/.env` from [`.env.example`](../backend/.env.example). Mongo only if you run full pytest/e2e — not required for gateway smoke alone.

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
| **4** | **speech_sidecar** | `7861` (localhost) | Whisper + Kokoro on CPU |

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

`COLAB_VLLM_URL=https://….trycloudflare.com/v1`

Optional: [notebook §8](me_mex_inference_stack.ipynb) installs the binary under `/usr/local/bin/cloudflared`; either path is fine.

### 3.3 Log files (all bring-up paths)

Every long-running process should append to **`colab/logs/`** on the Colab VM (not committed to git). Use **`tee -a`** so you still see output in tmux or notebook while persisting for later debugging.

| Log file | Process | Typical contents |
|----------|---------|------------------|
| `logs/vllm.log` | vLLM `:8000` | Model load, OOM, request errors |
| `logs/gateway.log` | `inference_gateway` `:7860` | Uvicorn access log, reranker load, proxy errors to vLLM/speech |
| `logs/speech.log` | `speech_sidecar` `:7861` | Whisper/Kokoro load (Phase 2) |
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

**Follow logs** from a notebook cell or the tmux `logs` window:

```bash
tail -F logs/vllm.log logs/gateway.log logs/speech.log logs/cloudflared.log
```

Download for offline debugging: Colab **Files** pane → `colab/logs/` → right-click → download. When reporting issues, attach the relevant `.log` snippets (startup through first error).

### 3.4 Recommended: **tmux** (one Colab terminal, four windows)

Colab does **not** provide multiple terminal tabs. Use **tmux** so each process has its own window and **tee** writes `logs/*.log`.

**One-time setup** (notebook cell or terminal):

```bash
apt-get update -qq && apt-get install -y -qq tmux
cd /content/me-mex/colab
chmod +x start_inference_tmux.sh
./start_inference_tmux.sh reasoning   # wraps §3.2 commands + tee
```

The helper script [start_inference_tmux.sh](./start_inference_tmux.sh) creates session **`me-mex-inference`** with windows:

| Window | Starts | Log file |
|--------|--------|----------|
| `vllm` | vLLM on `:8000` | `logs/vllm.log` |
| `speech` | speech sidecar `:7861` | `logs/speech.log` |
| `gateway` | waits ~90s, then gateway `:7860` | `logs/gateway.log` |
| `tunnel` | waits ~120s, then cloudflared → `:7860` | `logs/cloudflared.log` |
| `logs` | `tail -F` on all four logs | — |

**Attach** from Colab’s terminal: `tmux attach -t me-mex-inference`  
**Detach** (leave processes running): `Ctrl-b` then `d`  
**Switch window:** `Ctrl-b` then `w` (pick `vllm`, `gateway`, …) or `Ctrl-b n` / `p`

Copy the tunnel URL from **`logs/cloudflared.log`** or the `tunnel` window → Mac `COLAB_VLLM_URL=…/v1` (§4).

**Manual tmux:** create session `tmux new -s me-mex-inference`, one window per process; paste **§3.2** commands with `2>&1 | tee -a logs/<file>.log`.

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
COLAB_VLLM_URL=https://YOUR_SUBDOMAIN.trycloudflare.com/v1
CHAT_LLM_MODE=live
DECISION_SCORER_MODE=live
LLM_MODEL_NAME=mistralai/Ministral-3-8B-Reasoning-2512
LLM_TIMEOUT=180

# Phase 2 voice (same host, no /v1):
# COLAB_SPEECH_BASE_URL=https://YOUR_SUBDOMAIN.trycloudflare.com
```

`COLAB_VLLM_URL` **must end with `/v1`**. Backend uses:

- `{COLAB_VLLM_URL}/chat/completions`
- `{COLAB_VLLM_URL}/decision/score`

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
- [ ] Tunnel URL in `COLAB_VLLM_URL` (with `/v1`)
- [ ] `pytest -m vllm` (decision integration) green
- [ ] (Optional) `eval_decision_model.py --live` + saved report
- [ ] (Optional) full `uv run pytest` with Mongo

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| 404 on `/v1/decision/score` | Tunnel must target gateway **`:7860`**, not vLLM `:8000` |
| Decision fails, chat works | `COLAB_VLLM_URL` must include `/v1` |
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
| [speech_sidecar.py](./speech_sidecar.py) | Whisper + Kokoro |
| [requirements-colab.txt](./requirements-colab.txt) | Notebook pip pins |
| [TOPOLOGY.md](./TOPOLOGY.md) | Architecture diagram |
| [start_inference_tmux.sh](./start_inference_tmux.sh) | tmux session + `logs/*.log` via `tee` |
| `logs/` | Runtime log directory on Colab (gitignored `*.log`) |

---

## 10. Phase 2 voice

Same tunnel host; set `COLAB_SPEECH_BASE_URL` without `/v1`. LiveKit stays local. Notebook §10.
