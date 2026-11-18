from pathlib import Path

import pytest
from app.bootstrap.alignment import (
    build_alignment_report,
    build_root_indexes,
    is_excluded_top_section,
    parse_deeper_read_roots,
    parse_overall_insights,
    resolve_cite_token,
)
from app.bootstrap.decision_prompt import (
    build_decision_prompt,
    normalize_relevance_labels,
)
from app.bootstrap.emit_traces import emit_bootstrap_rows


def test_excluded_overall_insights_sections(tmp_path: Path):
    p = tmp_path / "overall_insights.md"
    p.write_text(
        "## VLAs\n\n1. Keep (ERA).\n\n## General Notes\n\n1. Skip (ERA).\n",
        encoding="utf-8",
    )
    _sections, insights = parse_overall_insights(p)
    assert len(insights) == 1
    assert is_excluded_top_section("General Notes")
    assert is_excluded_top_section("Podcast")


def test_cite_with_comma_in_title_not_split(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "deeper_read_notes.md").write_text(
        "### Partition the Support, Reconstruct the Residual: 2608.18484\nGist.\n",
        encoding="utf-8",
    )
    (docs / "overall_insights.md").write_text(
        "## VLAs\n\n1. Note (Partition the Support, Reconstruct the Residual).\n",
        encoding="utf-8",
    )
    report, _roots, *_ = build_alignment_report(docs)
    assert any(
        l["cite_token"] == "Partition the Support, Reconstruct the Residual" for l in report.matched
    )
    assert "Partition the Support" not in [u["cite_token"] for u in report.unmatched]


def test_parse_deeper_read_url_header_alias(tmp_path: Path):
    p = tmp_path / "deeper_read_notes.md"
    p.write_text(
        "### DRIS: https://robotpilab.github.io/publication/drsscatch/rss2026.pdf\nGist.\n",
        encoding="utf-8",
    )
    roots = parse_deeper_read_roots(p)
    assert roots[0].short_label == "DRIS"
    indexes = build_root_indexes(roots)
    rid, method, _ = resolve_cite_token("DRIS", indexes)
    assert rid == roots[0].root_id
    assert method == "exact_short_label"


def test_parse_deeper_read_arxiv_header(tmp_path: Path):
    p = tmp_path / "deeper_read_notes.md"
    p.write_text(
        "## Section\n\n### ERA: 2510.12693\nFirst line gist.\nSecond line.\n",
        encoding="utf-8",
    )
    roots = parse_deeper_read_roots(p)
    assert len(roots) == 1
    assert roots[0].short_label == "ERA"
    assert roots[0].arxiv_id == "2510.12693"
    assert roots[0].root_id == "root_2510_12693"


def test_overall_insights_cites(tmp_path: Path):
    p = tmp_path / "overall_insights.md"
    p.write_text(
        "## VLAs\n\n### System Architecture\n\n1. Reasoning is key (ERA), other (TurboVLA).\n",
        encoding="utf-8",
    )
    sections, insights = parse_overall_insights(p)
    subs = [s for s in sections if s.level == 3]
    assert len(subs) == 1
    assert subs[0].flat_title == "VLAs — System Architecture"
    assert len(insights) == 1
    assert insights[0].section_id == subs[0].section_id
    assert insights[0].cite_tokens == ["ERA", "TurboVLA"]


def test_resolve_cite_exact():
    from app.bootstrap.alignment import RootRecord

    indexes = build_root_indexes(
        [
            RootRecord(
                root_id="root_2510_12693",
                short_label="ERA",
                arxiv_id="2510.12693",
                title="ERA: 2510.12693",
                gist="",
            )
        ]
    )
    rid, method, _ = resolve_cite_token("ERA", indexes)
    assert rid == "root_2510_12693"
    assert method == "exact_short_label"


def test_emit_traces_minimal(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "deeper_read_notes.md").write_text(
        "### ERA: 2510.12693\nGist.\n\n### TurboVLA: 2510.99999\nOther.\n",
        encoding="utf-8",
    )
    (docs / "overall_insights.md").write_text(
        "## VLAs\n\n### Architecture\n\n1. VLAs need reasoning (ERA).\n\n### Control\n\n1. Other topic (TurboVLA).\n",
        encoding="utf-8",
    )
    report, roots, sections, insights, _ = build_alignment_report(docs)
    rows = emit_bootstrap_rows(roots, sections, insights, report.insight_cite_links)
    assert len(rows) >= 1
    row = next(r for r in rows if r["query_node"]["id"] == "root_2510_12693")
    assert row["scenario"] == "placement_subsection"
    assert row["query_node"]["node_kind"] == "ROOT"
    assert all(n["node_kind"] == "CONCEPT_M" for n in row["frontier"])
    assert set(row["label_relevance"].keys()) == {n["id"] for n in row["frontier"]}
    assert abs(sum(row["label_relevance"].values()) - 1.0) < 1e-6
    gold = max(row["label_relevance"].items(), key=lambda x: x[1])[0]
    assert gold == row["user_expanded_ids"][0]


def test_decision_prompt_roundtrip():
    q = {"id": "q", "title": "Q", "node_kind": "ROOT", "gist": "g"}
    f = [{"id": "a", "title": "A", "node_kind": "CONCEPT_M"}]
    text = build_decision_prompt(q, f)
    assert "QUERY: id=q" in text
    assert "id=a" in text
    assert normalize_relevance_labels({"a": 1.0}) == {"a": 1.0}


def test_real_docs_if_present():
    docs = Path(__file__).resolve().parents[5] / "docs"
    if not (docs / "deeper_read_notes.md").exists():
        pytest.skip("cortex-os docs not present")
    roots = parse_deeper_read_roots(docs / "deeper_read_notes.md")
    assert len(roots) > 50
    report, *_ = build_alignment_report(docs)
    assert report.summary()["matched"] > 100
