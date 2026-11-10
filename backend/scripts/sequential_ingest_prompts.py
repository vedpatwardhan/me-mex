#!/usr/bin/env python3
"""
Run ingestion prompts from prompts.json through the orchestrator (HTTP API), one after another.

Requires the Me-Mex backend to be running (e.g. uvicorn main:app --port 8000).

Usage (do not run until you are ready):
  cd me-mex/backend
  python3 scripts/sequential_ingest_prompts.py
  python3 scripts/sequential_ingest_prompts.py --dry-run
  python3 scripts/sequential_ingest_prompts.py --base-url http://127.0.0.1:8000 --project-id global
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

# Default: cortex-os/prompts.json (sibling of me-mex/)
DEFAULT_PROMPTS_PATH = Path(__file__).resolve().parents[2].parent / "prompts.json"


def load_prompts(path: Path) -> List[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array of prompt strings")
    prompts = [p.strip() for p in data if isinstance(p, str) and p.strip()]
    if not prompts:
        raise ValueError(f"{path}: no non-empty prompts")
    return prompts


def parse_sse_data_line(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload:
        return None
    return json.loads(payload)


def run_stream_turn(
    client: httpx.Client,
    base_url: str,
    query: str,
    project_id: str,
    chat_history: List[Dict[str, str]],
    verbose: bool,
) -> Tuple[str, List[Dict[str, str]], bool]:
    """POST /api/chat/stream; return (assistant_reply, updated_history, success)."""
    url = f"{base_url.rstrip('/')}/api/chat/stream"
    body = {
        "query": query,
        "project_id": project_id,
        "is_voice": False,
        "chat_history": chat_history,
    }
    reply_parts: List[str] = []
    success = True
    intent = "CONVERSATION"

    with client.stream("POST", url, json=body) as response:
        if response.status_code != 200:
            text = response.read().decode("utf-8", errors="replace")
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code}: {text}",
                request=response.request,
                response=response,
            )
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                event = parse_sse_data_line(raw_line)
            except json.JSONDecodeError:
                continue
            if not event:
                continue
            evt = event.get("event")
            if verbose and evt not in ("token_chunk",):
                print(f"    event: {evt}")
            if evt == "intent_classified":
                intent = event.get("intent", intent)
            elif evt == "token_chunk":
                reply_parts.append(event.get("delta", ""))
            elif evt == "chat_complete":
                if not reply_parts:
                    reply_parts.append(event.get("final_answer", ""))
            elif evt == "ingestion_completed":
                doc = event.get("doc_title") or event.get("message") or "document"
                print(f"    ✓ ingestion_completed: {doc}")
            elif evt == "ingestion_phase_timings":
                timings = event.get("phase_timings") or event
                total = timings.get("total_ingestion") or timings.get("total")
                if total is not None:
                    print(f"    phase total_ingestion: {total}s")
            elif evt in ("error", "ingestion_error"):
                success = False
                print(f"    ✗ {evt}: {event.get('message', event)}", file=sys.stderr)

    assistant_reply = "".join(reply_parts).strip() or f"Processed ({intent})."
    updated = list(chat_history)
    updated.append({"role": "user", "content": query})
    updated.append({"role": "assistant", "content": assistant_reply})
    return assistant_reply, updated, success


def run_json_turn(
    client: httpx.Client,
    base_url: str,
    query: str,
    project_id: str,
    chat_history: List[Dict[str, str]],
) -> Tuple[str, List[Dict[str, str]], bool]:
    """POST /api/chat (non-streaming)."""
    url = f"{base_url.rstrip('/')}/api/chat"
    body = {
        "query": query,
        "project_id": project_id,
        "is_voice": False,
        "chat_history": chat_history,
    }
    response = client.post(url, json=body)
    response.raise_for_status()
    data = response.json()
    assistant_reply = (data.get("reply") or "").strip() or "Processed."
    success = data.get("status") == "success"
    updated = list(chat_history)
    updated.append({"role": "user", "content": query})
    updated.append({"role": "assistant", "content": assistant_reply})
    return assistant_reply, updated, success


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send prompts.json ingestion queries to the orchestrator sequentially."
    )
    parser.add_argument(
        "--prompts-file",
        type=Path,
        default=DEFAULT_PROMPTS_PATH,
        help=f"JSON array of prompt strings (default: {DEFAULT_PROMPTS_PATH})",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Me-Mex backend base URL",
    )
    parser.add_argument(
        "--project-id",
        default="global",
        help="Project workspace id",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        metavar="N",
        help="1-based index of first prompt to run (for resume)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Use POST /api/chat instead of /api/chat/stream",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print non-token SSE events",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List prompts and exit without calling the API",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=7200.0,
        help="Per-request read timeout in seconds (default 2h)",
    )
    args = parser.parse_args()

    prompts = load_prompts(args.prompts_file)
    if args.start < 1 or args.start > len(prompts):
        print(f"--start must be between 1 and {len(prompts)}", file=sys.stderr)
        return 2

    subset = prompts[args.start - 1 :]
    print(f"Loaded {len(prompts)} prompt(s) from {args.prompts_file}")
    if args.start > 1:
        print(f"Resuming from prompt #{args.start}")

    if args.dry_run:
        for i, p in enumerate(prompts, start=1):
            mark = ">" if i >= args.start else " "
            print(f"{mark} {i:2d}. {p[:100]}{'...' if len(p) > 100 else ''}")
        return 0

    timeout = httpx.Timeout(connect=30.0, read=args.timeout, write=30.0, pool=30.0)
    failures: List[int] = []
    chat_history: List[Dict[str, str]] = []

    with httpx.Client(timeout=timeout) as client:
        try:
            health = client.get(f"{args.base_url.rstrip('/')}/api/projects")
            health.raise_for_status()
        except httpx.HTTPError as e:
            print(
                f"Cannot reach backend at {args.base_url} ({e}). "
                "Start uvicorn first.",
                file=sys.stderr,
            )
            return 1

        for offset, query in enumerate(subset):
            index = args.start + offset
            print(
                f"\n[{index}/{len(prompts)}] {query[:120]}{'...' if len(query) > 120 else ''}"
            )
            t0 = time.time()
            try:
                if args.no_stream:
                    _, chat_history, ok = run_json_turn(
                        client, args.base_url, query, args.project_id, chat_history
                    )
                else:
                    _, chat_history, ok = run_stream_turn(
                        client,
                        args.base_url,
                        query,
                        args.project_id,
                        chat_history,
                        args.verbose,
                    )
                elapsed = time.time() - t0
                print(f"    done in {elapsed:.1f}s")
                if not ok:
                    failures.append(index)
            except httpx.HTTPError as e:
                print(f"    ✗ request failed: {e}", file=sys.stderr)
                failures.append(index)
                break

    if failures:
        print(
            f"\nFinished with failures at prompt index(es): {failures}", file=sys.stderr
        )
        return 1
    print(f"\nAll {len(subset)} prompt(s) completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
