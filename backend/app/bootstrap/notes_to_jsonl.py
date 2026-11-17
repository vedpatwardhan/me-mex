"""Join deeper_read_notes + overall_insights → decision trace JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.bootstrap.alignment import build_alignment_report
from app.bootstrap.emit_traces import emit_bootstrap_rows
from app.config import ROOT_DIR, settings


def write_alignment_markdown(report_path: Path, data: dict) -> None:
    md_path = report_path.with_suffix(".md")
    s = data["summary"]
    lines = [
        "# Alignment report",
        "",
        f"roots={s['roots']} cites_extracted={s['cites_extracted']} "
        f"matched={s['matched']} unmatched={s['unmatched']} "
        f"ambiguous={s['ambiguous']} orphan_roots={s['orphan_roots']}",
        "",
        "## Unmatched (fix cites in overall_insights or deeper_read)",
        "",
    ]
    for u in data["unmatched"][:80]:
        cands = ", ".join(
            f"{c['short_label']}({c['score']})" for c in u.get("candidates", [])[:3]
        )
        lines.append(
            f"- L{u['line_no']} `{u['cite_token']}` — {u['snippet'][:100]}… "
            f"candidates: {cands}"
        )
    if len(data["unmatched"]) > 80:
        lines.append(f"- … and {len(data['unmatched']) - 80} more")
    lines.extend(["", "## Ambiguous", ""])
    for a in data["ambiguous"][:30]:
        cands = ", ".join(c["short_label"] for c in a.get("candidates", [])[:3])
        lines.append(f"- L{a['line_no']} `{a['cite_token']}` → {cands}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap decision JSONL from notes")
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=ROOT_DIR.parent / "docs",
        help="cortex-os docs (deeper_read_notes + overall_insights)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(settings.DECISION_TRAINING_DIR) / "robotics" / "bootstrap.jsonl",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Write alignment report only (no JSONL)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(settings.DECISION_TRAINING_DIR)
        / "robotics"
        / "alignment_report.json",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Refuse to emit JSONL if unmatched cites remain",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    report, roots, sections, insights, _indexes = build_alignment_report(args.docs_dir)
    data = report.to_dict()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(data, indent=2), encoding="utf-8")
    write_alignment_markdown(args.report, data)

    summary = report.summary()
    print(
        f"matched={summary['matched']} unmatched={summary['unmatched']} "
        f"ambiguous={summary['ambiguous']} roots={summary['roots']} "
        f"cites_extracted={summary['cites_extracted']}"
    )
    print(f"Wrote {args.report} and {args.report.with_suffix('.md')}")

    if args.report_only:
        return

    if args.strict and summary["unmatched"] > 0:
        raise SystemExit(
            f"strict: {summary['unmatched']} unmatched cites — fix docs and re-run --report-only"
        )

    rows = emit_bootstrap_rows(
        roots,
        sections,
        insights,
        report.insight_cite_links,
        seed=args.seed,
    )
    if not rows:
        raise SystemExit("No bootstrap rows emitted (no matched insight→ROOT links?)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
