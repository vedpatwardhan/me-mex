import os
import json
import time
import inspect
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextvars import ContextVar

# Context variable to track active trace session per request / async task
_current_session_id: ContextVar[Optional[str]] = ContextVar(
    "current_session_id", default=None
)
_current_step_counter: ContextVar[int] = ContextVar("current_step_counter", default=0)

BASE_TRACE_DIR = Path(
    os.getenv(
        "ME_MEX_TRACE_DIR",
        Path(__file__).resolve().parent.parent.parent / "logs" / "llm_traces",
    )
)


class LLMTracer:
    """
    Local JSON-based LLM Call Tracer.
    Records complete input prompts, structured output schemas, raw responses,
    durations, and caller metadata to local disk for offline inspection and debugging.
    """

    def __init__(self, base_dir: Path = BASE_TRACE_DIR):
        self.base_dir = base_dir

    def start_session(self, session_prefix: str = "session") -> str:
        """Starts a new trace session and resets step counter for the current context."""
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = (
            f"{session_prefix}_{timestamp_str}_{int(time.time() * 1000) % 10000:04d}"
        )
        _current_session_id.set(session_id)
        _current_step_counter.set(0)
        return session_id

    def get_session_id(self) -> str:
        """Retrieves or auto-initializes the current session ID."""
        sid = _current_session_id.get()
        if not sid:
            sid = self.start_session("default")
        return sid

    def _resolve_caller(self, caller: Optional[str]) -> str:
        """Fallback to inspect call stack if caller was not explicitly provided."""
        if caller:
            return caller

        try:
            stack = inspect.stack()
            # Traverse frames backwards skipping tracer and gateway frames
            for frame_info in stack[2:]:
                fn = frame_info.function
                file_name = Path(frame_info.filename).name
                if file_name in ("llm_tracer.py", "llm_gateway.py"):
                    continue
                cls_name = None
                if "self" in frame_info.frame.f_locals:
                    cls_name = frame_info.frame.f_locals["self"].__class__.__name__
                if cls_name:
                    return f"{cls_name}.{fn}"
                return f"{file_name}:{fn}"
        except Exception:
            pass

        return "unknown_caller"

    def log_call(
        self,
        caller: Optional[str],
        model: str,
        messages: List[Dict[str, Any]],
        duration_seconds: float,
        temperature: float,
        max_tokens: int,
        response_raw: Optional[str] = None,
        response_parsed: Optional[Any] = None,
        response_model_name: Optional[str] = None,
        attempts: int = 1,
        status: str = "SUCCESS",
        error: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Writes a full-payload trace JSON file and appends an entry to index.jsonl.
        Guaranteed fail-safe: disk I/O errors never raise to the caller.
        """
        try:
            resolved_caller = self._resolve_caller(caller)
            session_id = self.get_session_id()

            # Increment step counter
            step_idx = _current_step_counter.get() + 1
            _current_step_counter.set(step_idx)

            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            session_dir = self.base_dir / "runs" / date_str / session_id
            session_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize caller for filename
            clean_caller = "".join(
                c if (c.isalnum() or c in "._-[]") else "_" for c in resolved_caller
            )
            trace_filename = f"{step_idx:02d}_{clean_caller}.json"
            trace_path = session_dir / trace_filename

            trace_data = {
                "trace_id": f"trace_{int(time.time() * 1000)}_{step_idx:02d}",
                "session_id": session_id,
                "step_index": step_idx,
                "caller": resolved_caller,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_model": response_model_name,
                "timestamp": time.time(),
                "duration_seconds": round(duration_seconds, 3),
                "status": status,
                "attempts": attempts,
                "request": {
                    "messages": messages,
                },
                "response": {
                    "raw_text": response_raw,
                    "parsed": response_parsed,
                },
                "error": error,
            }

            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump(trace_data, f, indent=2, default=str)

            # Append to master index.jsonl
            index_path = self.base_dir / "index.jsonl"
            index_entry = {
                "timestamp": trace_data["timestamp"],
                "session_id": session_id,
                "step_index": step_idx,
                "caller": resolved_caller,
                "model": model,
                "duration_seconds": trace_data["duration_seconds"],
                "status": status,
                "file_path": str(trace_path.relative_to(self.base_dir)),
            }
            with open(index_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(index_entry) + "\n")

            return trace_path
        except Exception as e:
            # Completely fail-safe: never disrupt main application logic
            print(f"[LLMTracer Warning] Failed to log trace: {e}")
            return None


# Global singleton instance
llm_tracer = LLMTracer()
