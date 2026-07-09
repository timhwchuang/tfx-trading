"""Query spec parsing for SessionBars.get()."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

QueryKind = Literal[
    "series",
    "last",
    "current",
    "ma",
    "mas",
    "closes",
    "today",
]

_DAILY_ALIASES = frozenset({"daily", "1d", "d"})
_MA_RE = re.compile(r"^(?:ma(\d+)|(\d+)ma)$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedQuery:
    tf: str
    kind: QueryKind
    n: int | None = None
    ma_period: int | None = None


def normalize_tf(tf: str) -> str:
    key = tf.strip().lower()
    if key in _DAILY_ALIASES:
        return "daily"
    if key == "today":
        return "today"
    return key


def parse_query(tf: str, spec: str | int | None) -> ParsedQuery:
    """Parse ``get(tf, spec)`` into a normalized query."""
    norm_tf = normalize_tf(tf)
    if norm_tf == "today":
        return ParsedQuery(tf="today", kind="today")

    if spec is None:
        return ParsedQuery(tf=norm_tf, kind="series")

    if isinstance(spec, int):
        if spec <= 0:
            raise ValueError(f"bar count must be positive, got {spec}")
        return ParsedQuery(tf=norm_tf, kind="series", n=spec)

    token = spec.strip().lower()
    if token == "last":
        return ParsedQuery(tf=norm_tf, kind="last")
    if token == "current":
        return ParsedQuery(tf=norm_tf, kind="current")
    if token == "closes":
        return ParsedQuery(tf=norm_tf, kind="closes")
    if token == "mas":
        if norm_tf != "daily":
            raise KeyError(f"'mas' is only valid for daily, got {tf!r}")
        return ParsedQuery(tf=norm_tf, kind="mas")

    ma_match = _MA_RE.match(token)
    if ma_match:
        period = int(ma_match.group(1) or ma_match.group(2))
        if period <= 0:
            raise ValueError(f"MA period must be positive, got {period}")
        return ParsedQuery(tf=norm_tf, kind="ma", ma_period=period)

    raise KeyError(
        f"unknown query spec {spec!r}; expected last, current, closes, mas, maN, Nma, or int"
    )


__all__ = ["ParsedQuery", "QueryKind", "normalize_tf", "parse_query"]