"""CLI catalog for trading-app — discovery + delegate to per-module --help."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent
_APP_SPEC_PATH = _SRC_DIR.parent / "SPEC.md"


@dataclass(frozen=True)
class CliEntry:
    module: str
    summary: str
    example: str


# Run from apps/trading-app/src with PYTHONPATH=. (or monorepo scripts).
CATALOG: tuple[CliEntry, ...] = (
    CliEntry("live", "模擬 / 正式連線交易（日盤+夜盤）", "python -m live"),
    CliEntry("storage", "tick_cache helpers（plain CSV SSOT）", "python -m storage"),
    CliEntry(
        "backfilldata",
        "永豐 API 補歷史 tick / kbar 快取（calendar-day AllDay）",
        "python -m backfilldata month 2026-04",
    ),
)


def parse_spec_cli_modules(spec_path: Path | None = None) -> frozenset[str]:
    """Parse module names from apps/trading-app/SPEC.md ## CLI table only (excludes cli_help)."""
    path = spec_path or _APP_SPEC_PATH
    text = path.read_text(encoding="utf-8")
    start = text.find("## CLI")
    if start < 0:
        return frozenset()
    rest = text[start:]
    end = rest.find("\n## ", 1)
    section = rest[:end] if end >= 0 else rest
    modules: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("| Command") or line.startswith("|---"):
            continue
        for match in re.finditer(r"`python -m ([\w.]+)", line):
            mod = match.group(1)
            if mod != "cli_help":
                modules.add(mod)
    return frozenset(modules)


def format_catalog() -> str:
    lines = [
        "trading-app CLI catalog",
        "",
        "前置（Windows 範例，monorepo 根）：",
        "  cd apps\\trading-app\\src",
        "  $env:PYTHONPATH = (Get-Location).Path",
        "",
        "指令一覽（細部參數請用下方 MODULE --help）：",
        "",
    ]
    name_w = max(len(e.module) for e in CATALOG)
    for entry in CATALOG:
        lines.append(f"  {entry.module.ljust(name_w)}  {entry.summary}")
        lines.append(f"    {'':<{name_w}}  例：{entry.example}")
    lines.extend(
        [
            "",
            "查看單一指令說明：",
            "  python -m cli_help live",
            "  python -m live --help",
            "",
            "歷史研究工具見 legacy/（不在 active CLI）",
        ]
    )
    return "\n".join(lines)


def _pythonpath_entries() -> list[str]:
    return [str(_SRC_DIR)]


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    for entry in reversed(_pythonpath_entries()):
        if entry not in parts:
            parts.insert(0, entry)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def run_module_help(module: str) -> int:
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        check=False,
        cwd=_SRC_DIR,
        env=_subprocess_env(),
    )
    return int(result.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List trading-app CLI entry points and show per-module --help.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m cli_help\n"
            "  python -m cli_help live\n"
            "  python -m cli_help storage\n"
        ),
    )
    parser.add_argument(
        "module",
        nargs="?",
        help="Optional module name from catalog (runs MODULE --help)",
    )
    args = parser.parse_args(argv)

    known = {e.module for e in CATALOG}
    if args.module:
        if args.module not in known:
            print(f"未知模組: {args.module}", file=sys.stderr)
            print(f"可用: {', '.join(sorted(known))}", file=sys.stderr)
            return 1
        return run_module_help(args.module)

    print(format_catalog())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
