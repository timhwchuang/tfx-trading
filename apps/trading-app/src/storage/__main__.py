"""CLI: tick_cache helpers (CSV-only SSOT)."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "tick_cache is plain CSV only. "
            "Loaders: storage.tick_loader / storage.kbar_loader. "
            "Backfill: python -m backfilldata. "
            "Audit/repair/migrate live under legacy/."
        ),
    )
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
