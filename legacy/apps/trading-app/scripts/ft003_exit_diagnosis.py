"""FT-003 Phase 3.6: append exit diagnosis to VOLATILITY_BASELINE.md."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reporting.exit_diagnosis import (
    diagnose_report,
    merge_exit_into_markdown,
    parse_exit_audits_from_log,
    render_exit_section,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="FT-003 exit diagnosis for Phase 3.6")
    parser.add_argument("--agent", required=True, help="workspace slug")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="baseline valid JSON (default: workspaces/<agent>/reports/baseline_valid.json)",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="baseline log (default: workspaces/<agent>/logs/baseline_valid.log)",
    )
    parser.add_argument(
        "--markdown-append",
        type=Path,
        default=root / "workspaces" / "VOLATILITY_BASELINE.md",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    ws = root / "workspaces" / args.agent
    report_path = args.report or (ws / "reports" / "baseline_valid.json")
    log_path = args.log or (ws / "logs" / "baseline_valid.log")

    if not report_path.is_file():
        raise SystemExit(f"report not found: {report_path}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    diagnosis = diagnose_report(report)
    log_stats = None
    if log_path.is_file():
        log_stats = parse_exit_audits_from_log(log_path)
        diagnosis["log_stats"] = log_stats

    section = render_exit_section(args.agent, report_path.relative_to(root), diagnosis, log_stats)

    if args.markdown_append:
        merge_exit_into_markdown(args.markdown_append, section, agent=args.agent)
        print(f"updated {args.markdown_append}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(diagnosis, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
