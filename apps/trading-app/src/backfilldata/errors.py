"""Shared backfill exceptions (leaf module — no storage/core imports)."""


class BackfillError(RuntimeError):
    """User-facing backfill failure (missing creds, invalid dates, etc.)."""
