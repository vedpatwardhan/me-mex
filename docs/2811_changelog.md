# 2811 changelog — voice-in / text-out (2026-11-28)

## Summary

Product voice is now **browser mic → Colab STT → transcript review → `POST /api/conversation/turn/stream` SSE → dock turn thread**. **LiveKit**, **`voice_worker/`**, and **agent TTS** are removed from the dev path. HITL approvals use **REST** (`POST /api/agent/resume`) only.

## Superseded (do not follow for new work)

| Doc | Section / claim | Replacement |
|-----|-----------------|-------------|
| `04-agent-orchestration.md` | LiveKit STT→TTS topology, §12.10–12.11 LiveKit bridge, plane-1 TTS normative text | This changelog + HTTP voice flow below |
| `06-workflows.md` | LiveKit room / mute tied to SFU worker | Voice rail mic session (`CaptureRail.tsx` + `dockTurnClient.ts`) |
| `11-testing.md` | `-m livekit`, voice worker smokes as CI gate | Default `uv run pytest` (no `livekit` marker); `dock_turn_plane` HTTP/SSE tests |
| `README.md` | LiveKit SFU + `voice_worker` mandatory | `./scripts/dev-stack.sh` → backend + frontend + Mongo only |
| `colab/TOPOLOGY.md`, `RUNBOOK.md` | TTS on every conversation turn latency budget | STT + LLM only; replies are **text** in dock |

## Still valid

- `POST /api/conversation/turn/stream`, Supervisor dispatch, Colab STT + LLM
- Dock turn thread (`dockStreamReducer`, `useDockState`)
- `GET /api/agent/session/events` SSE (proactive / job updates)
- HITL via `POST /api/agent/resume`

## New canonical flow

```
Browser mic (MediaRecorder)
  → POST /api/voice/stt/transcribe
  → Review UI (CaptureRail)
  → POST /api/conversation/turn/stream (SSE tokens / turn_end)
  → Dock right pane
Proactive: GET /api/agent/session/events → job_update / assistant_followup
Cancel turn: AbortController on stream + POST /api/conversation/turn/abort
```

## Testing notes

- **Removed:** `pytest.mark.livekit`, `voice_worker/tests/`, `backend/tests/integration/livekit/`
- **Kept:** `dock_turn_plane`, `test_conversation_turn_stream.py`, `dockStreamReducer.test.ts`

## Follow-up

Optional later pass: fold this changelog into `04-agent-orchestration.md` (deferred).
