"""One-time helpers for deprecated monorepo ``kbar_cache/`` → ``tick_cache/`` layout.

Plain CSV only — ignores leftover ``*.csv.gz``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from storage.cache_paths import DEFAULT_TICK_CACHE_DIR, _MONOREPO_ROOT

logger = logging.getLogger(__name__)

LEGACY_KBAR_CACHE_DIR = _MONOREPO_ROOT / "kbar_cache"

_LEGACY_WARNED = False


def legacy_kbar_cache_present() -> bool:
    """True when deprecated ``kbar_cache/`` still has ``*_kbars_*`` files."""
    if not LEGACY_KBAR_CACHE_DIR.is_dir():
        return False
    return any(LEGACY_KBAR_CACHE_DIR.glob("*_kbars_*"))


def warn_if_legacy_kbar_cache(*, cache_dir: Path | None = None) -> None:
    """Log once per process when old ``kbar_cache/`` may leave stale tick_cache kbars."""
    global _LEGACY_WARNED
    if _LEGACY_WARNED or not legacy_kbar_cache_present():
        return
    _LEGACY_WARNED = True
    dest = cache_dir or DEFAULT_TICK_CACHE_DIR
    logger.warning(
        "偵測到已廢棄的 kbar_cache/（程式僅讀 tick_cache/）。"
        "請執行: bash scripts/linux/migrate-legacy-kbar-cache.sh "
        "或 cd apps/trading-app/src && python -m storage.legacy_cache_migrate "
        "--cache-dir %s",
        dest,
    )


def _should_copy_legacy(src: Path, dst: Path) -> bool:
    """Copy when destination missing or legacy file is strictly newer (mtime)."""
    if not dst.is_file():
        return True
    if not src.is_file():
        return False
    return src.stat().st_mtime > dst.stat().st_mtime


def ensure_legacy_kbars_migrated(cache_dir: Path) -> int:
    """Auto-migrate ``kbar_cache/`` into *cache_dir* before reading kbars.

    Raises ``RuntimeError`` when legacy plain CSV files exist but could not be
    merged into *cache_dir*.
    """
    if not legacy_kbar_cache_present():
        return 0

    cache_dir = Path(cache_dir)
    n = migrate_legacy_kbar_cache(cache_dir)
    unmigrated: list[str] = []
    for src in sorted(LEGACY_KBAR_CACHE_DIR.glob("*_kbars_*.csv")):
        if not src.is_file() or src.name.endswith(".csv.gz"):
            continue
        if (cache_dir / src.name).is_file():
            continue
        unmigrated.append(src.name)

    if unmigrated:
        raise RuntimeError(
            "deprecated kbar_cache/ has kbars not present under tick_cache/: "
            f"{unmigrated}. Run: bash scripts/linux/migrate-legacy-kbar-cache.sh "
            f"--cache-dir {cache_dir}"
        )
    if n:
        logger.info("已自 kbar_cache/ 自動遷移 %d 個 kbar 檔至 %s", n, cache_dir)
    return n


def migrate_legacy_kbar_cache(
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
    *,
    dry_run: bool = False,
) -> int:
    """Copy plain ``kbar_cache/*_kbars_*.csv`` into *cache_dir* when newer/missing."""
    if not legacy_kbar_cache_present():
        return 0

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    for src in sorted(LEGACY_KBAR_CACHE_DIR.glob("*_kbars_*")):
        if not src.is_file():
            continue
        if src.name.endswith(".csv.gz") or not src.name.endswith(".csv"):
            logger.info("略過非 plain CSV（CSV-only）%s", src.name)
            continue
        dst = cache_dir / src.name
        if not _should_copy_legacy(src, dst):
            logger.info("略過（tick_cache 較新）%s", src.name)
            continue
        if dry_run:
            logger.info("dry-run: %s → %s", src, dst)
            copied += 1
            continue
        shutil.copy2(src, dst)
        logger.info("已遷移 %s → %s", src.name, cache_dir)
        copied += 1

    return copied


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate deprecated kbar_cache/*_kbars_*.csv into tick_cache/",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_TICK_CACHE_DIR,
        help="Destination tick_cache directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without writing",
    )
    args = parser.parse_args(argv)
    n = migrate_legacy_kbar_cache(args.cache_dir, dry_run=args.dry_run)
    logger.info("done | files=%d", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
