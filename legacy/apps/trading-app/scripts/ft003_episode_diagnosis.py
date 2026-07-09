"""FT-003 Phase 3.6: append entry funnel §C to VOLATILITY_BASELINE.md."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.entry_funnel import (
    build_entry_funnel_payload,
    load_entry_funnel_config,
    merge_entry_into_markdown,
    render_entry_section,
)
from reporting.uat_report import read_log_lines


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="FT-003 entry funnel diagnosis (Phase 3.6 §C)")
    parser.add_argument("--agent", required=True, help="workspace slug")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="baseline log (default: workspaces/<agent>/logs/baseline_valid.log)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="baseline valid JSON (default: workspaces/<agent>/reports/baseline_valid.json)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="agent config (default: workspaces/<agent>/config/config.yaml)",
    )
    parser.add_argument(
        "--markdown-append",
        type=Path,
        default=root / "workspaces" / "VOLATILITY_BASELINE.md",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=root / "workspaces" / "reports" / "entry_funnel.json",
    )
    args = parser.parse_args(argv)

    ws = root / "workspaces" / args.agent
    log_path = args.log or (ws / "logs" / "baseline_valid.log")
    report_path = args.report or (ws / "reports" / "baseline_valid.json")
    config_path = args.config or (ws / "config" / "config.yaml")

    if not log_path.is_file():
        raise SystemExit(f"log not found: {log_path}")
    if not report_path.is_file():
        raise SystemExit(f"report not found: {report_path}")
    if not config_path.is_file():
        raise SystemExit(f"config not found: {config_path}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    lines = read_log_lines([log_path])
    cfg = load_entry_funnel_config(config_path)

    payload = build_entry_funnel_payload(
        agent=args.agent,
        log_lines=lines,
        report=report,
        cfg=cfg,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
    )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")

    if args.markdown_append:
        section = render_entry_section(
            args.agent,
            log_path.relative_to(root),
            payload,
        )
        merge_entry_into_markdown(args.markdown_append, section, agent=args.agent)
        print(f"updated {args.markdown_append}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
