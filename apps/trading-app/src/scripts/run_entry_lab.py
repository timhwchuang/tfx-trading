"""CLI: Entry Lab export and analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reporting.entry_lab_config import SLUGS, SlugName, SplitName, baseline_path, entry_lab_root
from reporting.entry_lab_export import corpus_path, export_corpus, refresh_regime_in_corpus, run_gate_check
from reporting.entry_lab_reports import write_reports


def _parse_slugs(raw: str) -> list[SlugName]:
    if raw == "all":
        return list(SLUGS.keys())
    out: list[SlugName] = []
    for part in raw.split(","):
        part = part.strip()
        if part not in SLUGS:
            raise ValueError(f"unknown slug: {part}")
        out.append(part)  # type: ignore[arg-type]
    return out


def _parse_splits(raw: str) -> list[SplitName]:
    out: list[SplitName] = []
    for part in raw.split(","):
        part = part.strip()
        if part not in ("train", "valid"):
            raise ValueError(f"unknown split: {part}")
        out.append(part)  # type: ignore[arg-type]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entry Lab pipeline")
    parser.add_argument("--slug", default="all", help="gdc,gudt,frp,sfbt or all")
    parser.add_argument("--split", default="train", help="train,valid or train,valid")
    parser.add_argument(
        "--steps",
        default="export,gate_check,reports",
        help="export,gate_check,reports",
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    slugs = _parse_slugs(args.slug)
    splits = _parse_splits(args.split)
    steps = {s.strip() for s in args.steps.split(",")}

    if args.dry_run:
        for slug in slugs:
            spec = SLUGS[slug]
            for split in splits:
                exp = run_gate_check(
                    spec,
                    split,
                    exported_n=-1,
                    baseline_path=baseline_path(spec, split),
                )
                print(json.dumps({"slug": slug, "split": split, "expected": exp}, indent=2))
        return 0

    failed_gate = False
    if "export" in steps or "gate_check" in steps:
        for slug in slugs:
            spec = SLUGS[slug]
            for split in splits:
                if "export" in steps:
                    print(f"export {slug} {split}...")
                    result = export_corpus(
                        spec,
                        split,
                        cache_dir=args.cache_dir,
                        baseline_path=baseline_path(spec, split),
                    )
                    gate = result["gate_check"]
                    print(f"  n={gate['exported_n']} expected={gate['expected_n']} pass={gate['pass']}")
                    if not gate["pass"]:
                        failed_gate = True
                elif "gate_check" in steps:
                    corpus_file = corpus_path(spec, split)
                    if not corpus_file.is_file():
                        print(f"missing corpus {corpus_file}", file=sys.stderr)
                        failed_gate = True
                        continue
                    n = len(json.loads(corpus_file.read_text())["entries"])
                    gate = run_gate_check(
                        spec, split, exported_n=n, baseline_path=baseline_path(spec, split)
                    )
                    if not gate["pass"]:
                        failed_gate = True
                    print(json.dumps(gate, indent=2))

    if failed_gate:
        print("GATE CHECK FAILED — stop downstream", file=sys.stderr)
        return 1

    if "regime_refresh" in steps:
        for slug in slugs:
            spec = SLUGS[slug]
            for split in splits:
                print(f"regime_refresh {slug} {split}...")
                refresh_regime_in_corpus(spec, split, cache_dir=args.cache_dir)
        steps.discard("regime_refresh")

    if "reports" in steps:
        write_reports(splits=tuple(splits))
        print(f"reports -> {entry_lab_root() / 'reports'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
