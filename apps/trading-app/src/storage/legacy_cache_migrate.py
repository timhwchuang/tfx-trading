"""One-time helpers for deprecated monorepo ``kbar_cache/`` → ``tick_cache/`` layout."""

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

    Raises ``RuntimeError`` when legacy files exist but could not be merged
    into *cache_dir* (B-class must not proceed with invisible kbars).
    """
    if not legacy_kbar_cache_present():
        return 0

    cache_dir = Path(cache_dir)
    n = migrate_legacy_kbar_cache(cache_dir)
    unmigrated: list[str] = []
    for src in sorted(LEGACY_KBAR_CACHE_DIR.glob("*_kbars_*")):
        if not src.is_file():
            continue
        name = src.name
        plain = name.removesuffix(".gz") if name.endswith(".gz") else name
        gz = f"{plain}.gz"
        if (cache_dir / plain).is_file() or (cache_dir / gz).is_file():
            continue
        unmigrated.append(name)

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
    """Copy ``kbar_cache/*_kbars_*`` into *cache_dir* when newer or missing.

    Prefers legacy primary files over stale ``tick_cache`` mirrors from the old
    dual-tree layout. Returns number of files copied or updated.
    """
    if not legacy_kbar_cache_present():
        return 0

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    for src in sorted(LEGACY_KBAR_CACHE_DIR.glob("*_kbars_*")):
        if not src.is_file():
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
        if dst.name.endswith(".csv") and not dst.name.endswith(".csv.gz"):
            gz = cache_dir / f"{dst.name}.gz"
            if gz.is_file():
                gz.unlink()
        elif dst.name.endswith(".csv.gz"):
            plain = cache_dir / dst.name.removesuffix(".gz")
            if plain.is_file():
                plain.unlink()
        logger.info("已遷移 %s → %s", src.name, cache_dir)
        copied += 1

    return copied


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate deprecated kbar_cache/*_kbars_* into tick_cache/",
    )
    parser.add_argument(
        "--cache-dir",
        "--tick-cache-dir",
        type=Path,
        default=DEFAULT_TICK_CACHE_DIR,
        dest="cache_dir",
        help="Destination tick_cache root",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    n = migrate_legacy_kbar_cache(args.cache_dir, dry_run=args.dry_run)
    if n == 0 and not legacy_kbar_cache_present():
        logger.info("無 kbar_cache/ 可遷移")
    else:
        logger.info("完成 | %d file(s)%s", n, " (dry-run)" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
