"""Align deeper_read_notes ROOT catalog with overall_insights parenthetical cites."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

# Greedy (.+) so titles with commas match arXiv on the final colon (e.g. "A, B: 2608.18484")
ROOT_LINE = re.compile(r"^###\s+(.+):\s*(\d{4}\.\d{4,5})\s*$")
ROOT_LINE_PLAIN = re.compile(r"^###\s+(.+?)\s*$")
ARXIV_INLINE = re.compile(r"\b(\d{4}\.\d{4,5})\b")
PAREN_CITE = re.compile(r"\(([^)]+)\)")
NUMBERED_INSIGHT = re.compile(r"^\s*\d+\.\s+(.+)$")

AUTO_MATCH_THRESHOLD = 0.92
SUGGESTION_LIMIT = 3

# Top-level ## blocks in overall_insights.md omitted from bootstrap / alignment cites
EXCLUDED_TOP_LEVEL_SECTIONS = frozenset(
    {
        "general notes",
        "blogs",
        "podcast",
        "podcasts",
    }
)


def is_excluded_top_section(title: str) -> bool:
    return title.strip().lower() in EXCLUDED_TOP_LEVEL_SECTIONS


@dataclass
class RootRecord:
    root_id: str
    short_label: str
    arxiv_id: str | None
    title: str
    gist: str
    node_kind: str = "ROOT"


@dataclass
class InsightRecord:
    insight_id: str
    section_id: str
    subsection_id: str | None
    text: str
    line_no: int
    cite_tokens: list[str]


@dataclass
class SectionRecord:
    section_id: str
    title: str
    level: int
    parent_title: str | None = None
    flat_title: str | None = None


def _slug(s: str, max_len: int = 64) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower()).strip("_")
    return (s or "node")[:max_len]


def _norm_label(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s\-]", "", s)
    return s


def parse_deeper_read_roots(path: Path) -> list[RootRecord]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    records: list[RootRecord] = []
    chunks = re.split(r"(?=^###\s)", text, flags=re.MULTILINE)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("###"):
            continue
        lines = chunk.splitlines()
        first = lines[0].strip()
        arxiv: str | None = None
        m = ROOT_LINE.match(first)
        if m:
            short_label, arxiv = m.group(1).strip(), m.group(2).strip()
            root_id = f"root_{arxiv.replace('.', '_')}"
            title = f"{short_label}: {arxiv}"
        else:
            m2 = ROOT_LINE_PLAIN.match(first)
            if not m2:
                continue
            header_rest = m2.group(1).strip()
            # ### ERA: 2510.xxx handled above; ### DRIS: https://... → match cite "DRIS"
            short_label = header_rest
            if ": " in header_rest:
                left, right = header_rest.split(":", 1)
                right = right.strip()
                if not re.match(r"^\d{4}\.\d{4,5}\s*$", right):
                    short_label = left.strip()
            arx_m = ARXIV_INLINE.search(chunk)
            arxiv = arx_m.group(1) if arx_m else None
            root_id = (
                f"root_{arxiv.replace('.', '_')}"
                if arxiv
                else f"root_{_slug(short_label)}"
            )
            title = header_rest if not arxiv else f"{short_label}: {arxiv}"
        gist = " ".join(ln.strip() for ln in lines[1:] if ln.strip())[:500]
        records.append(
            RootRecord(
                root_id=root_id,
                short_label=short_label,
                arxiv_id=arxiv,
                title=title,
                gist=gist,
            )
        )
    return records


def parse_overall_insights(
    path: Path,
) -> tuple[list[SectionRecord], list[InsightRecord]]:
    if not path.exists():
        return [], []
    sections: list[SectionRecord] = []
    insights: list[InsightRecord] = []
    current_section: SectionRecord | None = None
    current_sub: SectionRecord | None = None
    skip_branch = False
    insight_idx = 0

    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            title = line[3:].strip()
            skip_branch = is_excluded_top_section(title)
            current_sub = None
            if skip_branch:
                current_section = None
                continue
            current_section = SectionRecord(
                section_id=f"sec_{_slug(title)}",
                title=title,
                level=2,
                flat_title=title,
            )
            sections.append(current_section)
            continue
        if line.startswith("### "):
            if skip_branch or current_section is None:
                current_sub = None
                continue
            title = line[4:].strip()
            parent_title = current_section.title
            flat = f"{parent_title} — {title}"
            current_sub = SectionRecord(
                section_id=f"sub_{_slug(flat)}",
                title=title,
                level=3,
                parent_title=parent_title,
                flat_title=flat,
            )
            sections.append(current_sub)
            continue
        m = NUMBERED_INSIGHT.match(line)
        if m and current_section and not skip_branch:
            text = m.group(1).strip()
            tokens: list[str] = []
            for paren in PAREN_CITE.findall(text):
                paren = paren.strip()
                if paren:
                    tokens.append(paren)
            insight_idx += 1
            sec_id = (
                current_sub.section_id if current_sub else current_section.section_id
            )
            insights.append(
                InsightRecord(
                    insight_id=f"ins_{insight_idx:04d}",
                    section_id=sec_id,
                    subsection_id=current_sub.section_id if current_sub else None,
                    text=text,
                    line_no=i,
                    cite_tokens=tokens,
                )
            )
    return sections, insights


def _split_cite_tokens(token: str, indexes: dict[str, Any] | None = None) -> list[str]:
    """Split parenthetical cite lists; keep comma-in-title as one token when it matches a ROOT."""
    whole = token.strip()
    if not whole:
        return []
    if indexes is not None:
        rid, _, _ = resolve_cite_token(whole, indexes)
        if rid:
            return [whole]
    parts = [p.strip() for p in re.split(r",|/|&", whole) if p.strip()]
    if len(parts) <= 1:
        return parts or [whole]
    if indexes is None:
        return parts
    # Multi-cite paren: only split when the full string is not a known ROOT title
    resolved = [_split_cite_tokens(p, indexes) for p in parts]
    flat = [t for sub in resolved for t in sub]
    return flat


def build_root_indexes(roots: list[RootRecord]) -> dict[str, Any]:
    by_short: dict[str, str] = {}
    by_norm_short: dict[str, str] = {}
    by_arxiv: dict[str, str] = {}
    for r in roots:
        by_short[r.short_label.upper()] = r.root_id
        by_norm_short[_norm_label(r.short_label)] = r.root_id
        if r.arxiv_id:
            by_arxiv[r.arxiv_id] = r.root_id
    return {
        "by_short": by_short,
        "by_norm_short": by_norm_short,
        "by_arxiv": by_arxiv,
        "roots": {r.root_id: r for r in roots},
    }


def _fuzzy_candidates(token: str, roots: list[RootRecord]) -> list[dict[str, Any]]:
    n_tok = _norm_label(token)
    scored: list[tuple[float, RootRecord]] = []
    for r in roots:
        n_short = _norm_label(r.short_label)
        score = SequenceMatcher(None, n_tok, n_short).ratio()
        if n_tok in n_short or n_short in n_tok:
            score = max(score, 0.85)
        scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, r in scored[:SUGGESTION_LIMIT]:
        out.append(
            {
                "root_id": r.root_id,
                "short_label": r.short_label,
                "score": round(score, 3),
            }
        )
    return out


def resolve_cite_token(
    token: str, indexes: dict[str, Any]
) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    """Return (root_id, match_method, fuzzy_candidates)."""
    roots: dict[str, RootRecord] = indexes["roots"]
    root_list = list(roots.values())
    t = token.strip()
    if not t:
        return None, None, []

    arx = ARXIV_INLINE.search(t)
    if arx and arx.group(1) in indexes["by_arxiv"]:
        rid = indexes["by_arxiv"][arx.group(1)]
        return rid, "arxiv", []

    if t.upper() in indexes["by_short"]:
        return indexes["by_short"][t.upper()], "exact_short_label", []

    norm = _norm_label(t)
    if norm in indexes["by_norm_short"]:
        return indexes["by_norm_short"][norm], "normalized_short_label", []

    candidates = _fuzzy_candidates(t, root_list)
    if candidates and candidates[0]["score"] >= AUTO_MATCH_THRESHOLD:
        top = candidates[0]
        if len(candidates) > 1 and candidates[1]["score"] >= AUTO_MATCH_THRESHOLD:
            return None, None, candidates
        return top["root_id"], "fuzzy_auto", candidates
    return None, None, candidates


@dataclass
class AlignmentReport:
    roots_indexed: list[dict[str, Any]] = field(default_factory=list)
    cites_extracted: int = 0
    matched: list[dict[str, Any]] = field(default_factory=list)
    unmatched: list[dict[str, Any]] = field(default_factory=list)
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    orphan_roots: list[dict[str, Any]] = field(default_factory=list)
    insight_cite_links: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            "roots": len(self.roots_indexed),
            "cites_extracted": self.cites_extracted,
            "matched": len(self.matched),
            "unmatched": len(self.unmatched),
            "ambiguous": len(self.ambiguous),
            "orphan_roots": len(self.orphan_roots),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "roots_indexed": self.roots_indexed,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "orphan_roots": self.orphan_roots,
            "insight_cite_links": self.insight_cite_links,
        }


def build_alignment_report(
    docs_dir: Path,
    *,
    deeper_name: str = "deeper_read_notes.md",
    insights_name: str = "overall_insights.md",
) -> AlignmentReport:
    roots = parse_deeper_read_roots(docs_dir / deeper_name)
    sections, insights = parse_overall_insights(docs_dir / insights_name)
    indexes = build_root_indexes(roots)
    report = AlignmentReport()
    report.roots_indexed = [
        {
            "root_id": r.root_id,
            "short_label": r.short_label,
            "arxiv_id": r.arxiv_id,
            "title": r.title,
        }
        for r in roots
    ]

    cited_root_ids: set[str] = set()
    cite_count = 0
    for ins in insights:
        for raw_tok in ins.cite_tokens:
            for tok in _split_cite_tokens(raw_tok, indexes):
                cite_count += 1
                rid, method, candidates = resolve_cite_token(tok, indexes)
                entry_base = {
                    "cite_token": tok,
                    "insight_id": ins.insight_id,
                    "line_no": ins.line_no,
                    "snippet": ins.text[:200],
                }
                if rid:
                    cited_root_ids.add(rid)
                    report.matched.append(
                        {**entry_base, "root_id": rid, "match_method": method}
                    )
                    report.insight_cite_links.append(
                        {
                            "insight_id": ins.insight_id,
                            "root_id": rid,
                            "cite_token": tok,
                        }
                    )
                elif (
                    candidates
                    and len(candidates) >= 2
                    and candidates[0]["score"] >= AUTO_MATCH_THRESHOLD
                ):
                    report.ambiguous.append(
                        {
                            **entry_base,
                            "candidates": candidates,
                        }
                    )
                else:
                    report.unmatched.append({**entry_base, "candidates": candidates})

    report.cites_extracted = cite_count
    for r in roots:
        if r.root_id not in cited_root_ids:
            report.orphan_roots.append(
                {"root_id": r.root_id, "short_label": r.short_label, "title": r.title}
            )

    return report, roots, sections, insights, indexes
