"""Turn journal, abort registry, effect ledger, and revert."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Any

from app.agents.session_events import publish_session_event
from app.services.checkpoints import JsonCheckpointStore

_checkpoint = JsonCheckpointStore()
_checkpoint_lock = threading.RLock()
_abort_lock = threading.Lock()
_aborted_turn_ids: set[str] = set()
_pending_baselines: dict[str, dict[str, Any]] = {}


def new_turn_id() -> str:
    return f"turn_{uuid.uuid4().hex[:12]}"


def register_abort(turn_id: str) -> None:
    with _abort_lock:
        _aborted_turn_ids.add(turn_id)


def clear_abort(turn_id: str) -> None:
    with _abort_lock:
        _aborted_turn_ids.discard(turn_id)


def is_aborted(turn_id: str | None) -> bool:
    if not turn_id:
        return False
    with _abort_lock:
        return turn_id in _aborted_turn_ids


def _load_state(thread_id: str) -> dict[str, Any]:
    with _checkpoint_lock:
        return _checkpoint.load(thread_id) or {}


def _save_state(thread_id: str, state: dict[str, Any]) -> None:
    with _checkpoint_lock:
        _checkpoint.save(thread_id, state)


def _routing_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "transcript_len": len(state.get("transcript") or []),
        "current_source": copy.deepcopy(state.get("current_source")),
        "last_route": state.get("last_route"),
        "recent_graph_changes": copy.deepcopy(state.get("recent_graph_changes") or []),
    }


def begin_turn_journal(thread_id: str, turn_id: str) -> dict[str, Any]:
    with _checkpoint_lock:
        state = _checkpoint.load(thread_id) or {}
        baseline = _routing_snapshot(state)
        _pending_baselines[turn_id] = baseline
        pending = {
            "turn_id": turn_id,
            "at": time.time(),
            "user_text": "",
            "assistant_text": "",
            "effects": [],
            "baseline": baseline,
        }
        state["pending_turn"] = pending
        _checkpoint.save(thread_id, state)
        return pending


def set_pending_user_text(thread_id: str, turn_id: str, text: str) -> None:
    with _checkpoint_lock:
        state = _checkpoint.load(thread_id) or {}
        pending = state.get("pending_turn") or {}
        if pending.get("turn_id") != turn_id:
            return
        pending["user_text"] = (text or "")[:2000]
        state["pending_turn"] = pending
        _checkpoint.save(thread_id, state)


def append_turn_effect(
    thread_id: str,
    *,
    turn_id: str,
    kind: str,
    forward: dict[str, Any],
    inverse: dict[str, Any] | None = None,
) -> None:
    with _checkpoint_lock:
        state = _checkpoint.load(thread_id) or {}
        pending = state.get("pending_turn") or {}
        if pending.get("turn_id") != turn_id:
            journal = list(state.get("turn_journal") or [])
            if journal and journal[-1].get("turn_id") == turn_id:
                effects = list(journal[-1].get("effects") or [])
            else:
                effects = []
            effects.append(
                {
                    "kind": kind,
                    "forward": forward,
                    "inverse": inverse or {},
                    "at": time.time(),
                    "causal_turn_id": turn_id,
                }
            )
            if journal and journal[-1].get("turn_id") == turn_id:
                journal[-1]["effects"] = effects
            else:
                journal.append({"turn_id": turn_id, "effects": effects})
            state["turn_journal"] = journal[-50:]
            _checkpoint.save(thread_id, state)
            return
        effects = list(pending.get("effects") or [])
        effects.append(
            {
                "kind": kind,
                "forward": forward,
                "inverse": inverse or {},
                "at": time.time(),
                "causal_turn_id": turn_id,
            }
        )
        pending["effects"] = effects
        state["pending_turn"] = pending
        _checkpoint.save(thread_id, state)


def commit_turn_journal(
    thread_id: str,
    turn_id: str,
    *,
    user_text: str,
    assistant_text: str,
    persisted_custom_fields: dict[str, Any] | None = None,
) -> None:
    with _checkpoint_lock:
        state = _checkpoint.load(thread_id) or {}
        pending = state.pop("pending_turn", None) or {}
        if pending.get("turn_id") != turn_id:
            pending = {
                "turn_id": turn_id,
                "effects": [],
                "at": time.time(),
                "baseline": _pending_baselines.pop(turn_id, {}),
            }
        entry = {
            "turn_id": turn_id,
            "at": pending.get("at") or time.time(),
            "user_text": (user_text or pending.get("user_text") or "")[:2000],
            "assistant_text": (assistant_text or "")[:4000],
            "effects": list(pending.get("effects") or []),
            "baseline": pending.get("baseline") or _pending_baselines.pop(turn_id, {}),
        }
        journal = list(state.get("turn_journal") or [])
        journal.append(entry)
        state["turn_journal"] = journal[-50:]
        transcript = list(state.get("transcript") or [])
        transcript.append({"role": "user", "text": entry["user_text"], "turn_id": turn_id})
        if assistant_text:
            transcript.append(
                {"role": "assistant", "text": entry["assistant_text"], "turn_id": turn_id}
            )
        state["transcript"] = transcript[-50:]
        if persisted_custom_fields is not None:
            state["persisted_custom_fields"] = persisted_custom_fields
        _checkpoint.save(thread_id, state)
    _pending_baselines.pop(turn_id, None)
    clear_abort(turn_id)


def rollback_pending_turn(thread_id: str, turn_id: str) -> None:
    with _checkpoint_lock:
        state = _checkpoint.load(thread_id) or {}
        pending = state.pop("pending_turn", None)
        if not pending or pending.get("turn_id") != turn_id:
            _checkpoint.save(thread_id, state)
            return
        baseline = pending.get("baseline") or _pending_baselines.pop(turn_id, {})
        transcript = list(state.get("transcript") or [])
        clip = int(baseline.get("transcript_len") or len(transcript))
        state["transcript"] = transcript[:clip]
        if baseline.get("current_source") is not None:
            state["current_source"] = baseline["current_source"]
        if baseline.get("last_route") is not None:
            state["last_route"] = baseline["last_route"]
        if baseline.get("recent_graph_changes") is not None:
            state["recent_graph_changes"] = baseline["recent_graph_changes"]
        _checkpoint.save(thread_id, state)
    _pending_baselines.pop(turn_id, None)
    clear_abort(turn_id)


def list_turn_journal(thread_id: str) -> list[dict[str, Any]]:
    return list(_load_state(thread_id).get("turn_journal") or [])


def revert_turn(*, thread_id: str, turn_id: str, store, project_id: str) -> dict[str, Any]:
    from app.agents import job_runtime
    from app.agents.turn_revert import apply_effect_inverse

    with _checkpoint_lock:
        state = _checkpoint.load(thread_id) or {}
        journal = list(state.get("turn_journal") or [])
        idx = next((i for i, row in enumerate(journal) if row.get("turn_id") == turn_id), None)
        if idx is None:
            raise ValueError("turn_id not found")
        removed = journal[idx:]
        removed_ids = {row.get("turn_id") for row in removed}
        effects: list[dict[str, Any]] = []
        for row in reversed(removed):
            for eff in reversed(row.get("effects") or []):
                if eff.get("causal_turn_id") in removed_ids:
                    effects.append(eff)

    blocking: list[str] = []
    for eff in effects:
        ok, reason = apply_effect_inverse(
            store=store,
            project_id=project_id,
            thread_id=thread_id,
            effect=eff,
        )
        if not ok:
            blocking.append(reason or eff.get("kind") or "unknown")

    if blocking:
        return {"ok": False, "blocking": blocking}

    for eff in effects:
        if eff.get("kind") == "job_dispatch":
            jid = (eff.get("forward") or {}).get("job_id")
            if jid:
                try:
                    job_runtime.control_job(thread_id, jid, "cancel", project_id=project_id)
                except ValueError:
                    pass
                try:
                    job_runtime.control_job(thread_id, jid, "delete", project_id=project_id)
                except ValueError:
                    pass
                from app.agents.session_plane import mark_job_history_reverted

                mark_job_history_reverted(thread_id, jid)

    with _checkpoint_lock:
        state = _checkpoint.load(thread_id) or {}
        journal = list(state.get("turn_journal") or [])
        idx = next((i for i, row in enumerate(journal) if row.get("turn_id") == turn_id), None)
        if idx is None:
            raise ValueError("turn_id not found")
        snap = journal[idx].get("baseline") or {}
        state["turn_journal"] = journal[:idx]
        transcript = []
        for row in state["turn_journal"]:
            transcript.append(
                {"role": "user", "text": row.get("user_text") or "", "turn_id": row.get("turn_id")}
            )
            if row.get("assistant_text"):
                transcript.append(
                    {
                        "role": "assistant",
                        "text": row.get("assistant_text") or "",
                        "turn_id": row.get("turn_id"),
                    }
                )
        state["transcript"] = transcript[-50:]
        if "current_source" in snap:
            state["current_source"] = snap["current_source"]
        if snap.get("last_route") is not None:
            state["last_route"] = snap["last_route"]
        if snap.get("recent_graph_changes") is not None:
            state["recent_graph_changes"] = snap["recent_graph_changes"]
        _checkpoint.save(thread_id, state)
        surviving = state["turn_journal"][-1] if state.get("turn_journal") else None

    publish_session_event(
        thread_id,
        {
            "type": "turn_reverted",
            "turn_id": turn_id,
            "removed_turn_ids": list(removed_ids),
        },
    )
    return {
        "ok": True,
        "turn_id": turn_id,
        "removed_count": len(removed),
        "removed_turn_ids": [row.get("turn_id") for row in removed],
        "latest_turn": surviving,
    }
