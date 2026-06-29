"""Generate Entry Lab markdown reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reporting.entry_lab_cohorts import (
    cohort_by_key,
    filter_intersection_matrix,
    summarize_cohort,
)
from reporting.entry_lab_config import SLUGS, SlugName, SplitName, entry_lab_root
from reporting.entry_lab_export import load_corpus
from reporting.entry_lab_paired import paired_gdc_gudt
from reporting.entry_lab_regime import regime_agreement_stats
from reporting.entry_lab_robustness import friction_sensitivity, regime_label_permutation_null


def analyze_slug(spec_slug: SlugName, split: SplitName) -> dict[str, Any]:
    spec = SLUGS[spec_slug]
    corpus = load_corpus(spec, split)
    rows = corpus.get("entries") or []
    baseline = summarize_cohort(rows)
    regime_cohorts = cohort_by_key(
        rows, lambda r: (r.get("alignment") or {}).get("r2", "unknown")
    )
    alignment_r1 = cohort_by_key(
        rows, lambda r: (r.get("alignment") or {}).get("r1", "unknown")
    )
    agreement = regime_agreement_stats(rows)
    robust = {
        "friction": friction_sensitivity(rows),
        "regime_perm": regime_label_permutation_null(rows),
    }
    return {
        "slug": spec_slug,
        "split": split,
        "tier": spec.tier,
        "n": len(rows),
        "baseline": baseline,
        "regime_r2_cohorts": regime_cohorts,
        "regime_r1_cohorts": alignment_r1,
        "regime_agreement": agreement,
        "robustness": robust,
    }


def build_intersection_filters(rows: list[dict[str, Any]], slug: str) -> dict[str, set[tuple[str, int]]]:
    from reporting.entry_lab_cohorts import entry_key

    filters: dict[str, set[tuple[str, int]]] = {}
    if slug in ("gdc", "gudt"):
        filters["gap_atr_high"] = {
            entry_key(r)
            for r in rows
            if r.get("gap_pts") is not None and r.get("atr")
            and abs(float(r["gap_pts"])) / float(r["atr"]) >= 1.0
        }
    if slug in ("frp", "sfbt"):
        filters["risk_unit_low"] = {
            entry_key(r)
            for r in rows
            if r.get("risk_unit") is not None and float(r["risk_unit"]) <= 12.0
        }
    filters["structure_long"] = {
        entry_key(r)
        for r in rows
        if (r.get("regime") or {}).get("structure_bias") == "Long"
    }
    filters["r2_with_trend"] = {
        entry_key(r)
        for r in rows
        if (r.get("alignment") or {}).get("r2") == "with_trend"
    }
    return filters


def write_reports(*, splits: tuple[SplitName, ...] = ("train", "valid")) -> Path:
    root = entry_lab_root() / "reports"
    root.mkdir(parents=True, exist_ok=True)

    all_analyses: dict[str, Any] = {}
    matrix_rows: list[str] = []

    for slug in SLUGS:
        for split in splits:
            try:
                analysis = analyze_slug(slug, split)
            except FileNotFoundError:
                continue
            key = f"{slug}_{split}"
            all_analyses[key] = analysis
            (root / f"{slug}_{split}_analysis.json").write_text(
                json.dumps(analysis, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            b = analysis["baseline"]
            path = b.get("path") or {}
            matrix_rows.append(
                f"| {slug} | {split} | {analysis['n']} | {path.get('pct_w30_pos')} | "
                f"{b.get('contract', {}).get('exit_gap_median')} | {b.get('tier')} |"
            )

    # Paired GDC/GUDT train
    paired_block = ""
    try:
        gdc = load_corpus(SLUGS["gdc"], "train")["entries"]
        gudt = load_corpus(SLUGS["gudt"], "train")["entries"]
        paired = paired_gdc_gudt(gdc, gudt)
        (root / "paired_gdc_gudt_train.json").write_text(
            json.dumps(paired, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        paired_block = (
            f"\n## Paired GDC barrier vs GUDT trail (train)\n\n"
            f"- n_paired: {paired.get('n_paired')}\n"
            f"- delta_net_median: {paired.get('delta_net_median')}\n"
            f"- contract_flip_count: {paired.get('path_contract_flip_count')}\n"
        )
    except FileNotFoundError:
        paired_block = "\n## Paired\n\n(corpus not exported)\n"

    # Intersection for primary train
    filter_section = ""
    for slug in ("frp", "sfbt"):
        try:
            rows = load_corpus(SLUGS[slug], "train")["entries"]
            filt = build_intersection_filters(rows, slug)
            ix = filter_intersection_matrix(filt)
            (root / f"filter_intersection_{slug}_train.json").write_text(
                json.dumps(ix, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            filter_section += f"\n### {slug} train filter Jaccard\n\n```json\n{json.dumps(ix['jaccard'], indent=2)}\n```\n"
        except FileNotFoundError:
            pass

    baseline_md = f"""# Entry Lab Baseline

> Diagnostic only — not gate.

## Cross-thesis matrix

| slug | split | n | pct_w30_pos | exit_gap_med | tier |
|------|-------|---|-------------|--------------|------|
{chr(10).join(matrix_rows)}
{paired_block}
## Filter intersection (exploratory)

{filter_section}
"""
    (root / "ENTRY_LAB_BASELINE.md").write_text(baseline_md, encoding="utf-8")

    candidates = """# FILTER_CANDIDATES

## Hypotheses (0–3 · pending human review)

- (Populate after reviewing train cohorts with tier≥descriptive_only)

## Excluded

- Post-hoc grid rescue on MVPClosed FT
- Filters with Jaccard > 0.7 vs structure_long (pseudo-independent)

## Intersection

See `filter_intersection_*_train.json`
"""
    (root / "FILTER_CANDIDATES.md").write_text(candidates, encoding="utf-8")
    return root
