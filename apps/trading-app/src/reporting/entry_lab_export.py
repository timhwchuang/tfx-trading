"""Export Entry Lab corpus from sealed P0 builders."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from reporting.entry_lab_cohorts import attach_derived
from reporting.entry_lab_config import (
    SPLITS,
    SlugName,
    SlugSpec,
    SplitName,
    build_payload,
    entry_lab_root,
    expected_n_from_baseline,
    repo_root,
)
from reporting.entry_lab_regime import enrich_rows_with_regime


def _git_commit(root: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _round_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in sorted(row.items()):
        if isinstance(v, float):
            out[k] = round(v, 2)
        elif isinstance(v, dict):
            out[k] = _round_row(v) if k not in ("atr_barrier_sim", "atr_trail_sim", "fvg_mid_trail_sim") else v
        else:
            out[k] = v
    return out


def corpus_path(spec: SlugSpec, split: SplitName) -> Path:
    return entry_lab_root() / "corpus" / f"{spec.slug}_{split}_entries.json"


def export_corpus(
    spec: SlugSpec,
    split: SplitName,
    *,
    code: str = "TMFR1",
    cache_dir: Path | None = None,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root()
    cache = cache_dir or (root / "tick_cache")
    from_d, to_d = SPLITS[split]

    payload = build_payload(
        spec.builder_name,
        code=code,
        cache_dir=cache,
        from_date=from_d,
        to_date=to_d,
    )
    rows_by = payload.get("rows_by_param") or {}
    rows = [dict(r) for r in rows_by.get(spec.p0_key) or []]

    enrich_rows_with_regime(rows, code=code, cache_dir=cache)
    attach_derived(rows)
    entries = [_round_row(r) for r in rows]

    corpus_body: dict[str, Any] = {
        "schema_version": 1,
        "slug": spec.slug,
        "ft": spec.ft,
        "tier": spec.tier,
        "split": split,
        "p0_key": spec.p0_key,
        "from_date": from_d,
        "to_date": to_d,
        "code": code,
        "git_commit": _git_commit(root),
        "n": len(entries),
        "entries": entries,
    }

    body = json.dumps(corpus_body, ensure_ascii=False, sort_keys=True, indent=2)
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    corpus = {**corpus_body, "content_sha256": sha}

    out_path = corpus_path(spec, split)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(corpus, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )

    gate = run_gate_check(
        spec,
        split,
        exported_n=len(entries),
        baseline_path=baseline_path,
    )
    manifest_path = entry_lab_root() / "corpus" / "corpus_manifest.json"
    manifest = _load_manifest(manifest_path)
    manifest[f"{spec.slug}_{split}"] = {
        "path": str(out_path.relative_to(root)),
        "n": len(entries),
        "sha256": sha,
        "gate_check": gate,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return {"corpus": corpus, "gate_check": gate, "path": out_path}


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def run_gate_check(
    spec: SlugSpec,
    split: SplitName,
    *,
    exported_n: int,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    bpath = baseline_path or __import__(
        "reporting.entry_lab_config", fromlist=["baseline_path"]
    ).baseline_path(spec, split)
    expected = expected_n_from_baseline(bpath, spec.p0_key)
    passed = expected is not None and exported_n == expected
    return {
        "pass": passed,
        "exported_n": exported_n,
        "expected_n": expected,
        "baseline_path": str(bpath),
        "p0_key": spec.p0_key,
    }


def refresh_regime_in_corpus(
    spec: SlugSpec,
    split: SplitName,
    *,
    code: str = "TMFR1",
    cache_dir: Path | None = None,
) -> Path:
    """Re-join regime on existing corpus without re-running CF builders."""
    root = repo_root()
    cache = cache_dir or (root / "tick_cache")
    corpus = load_corpus(spec, split)
    rows = corpus.get("entries") or []
    enrich_rows_with_regime(rows, code=code, cache_dir=cache)
    attach_derived(rows)
    entries = [_round_row(r) for r in rows]

    corpus_body = {k: v for k, v in corpus.items() if k != "content_sha256"}
    corpus_body["entries"] = entries
    corpus_body["n"] = len(entries)

    body = json.dumps(corpus_body, ensure_ascii=False, sort_keys=True, indent=2)
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    out = {**corpus_body, "content_sha256": sha}

    path = corpus_path(spec, split)
    path.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")

    gate = run_gate_check(spec, split, exported_n=len(entries))
    manifest_path = entry_lab_root() / "corpus" / "corpus_manifest.json"
    manifest = _load_manifest(manifest_path)
    manifest[f"{spec.slug}_{split}"] = {
        "path": str(path.relative_to(root)),
        "n": len(entries),
        "sha256": sha,
        "gate_check": gate,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return path


def load_corpus(spec: SlugSpec, split: SplitName) -> dict[str, Any]:
    path = corpus_path(spec, split)
    return json.loads(path.read_text(encoding="utf-8"))

