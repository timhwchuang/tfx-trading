"""FT-018b Route A stack — re-export from strategy package (canonical)."""

from strategy_gudt_route_a.stack import (
    RouteAStackParams,
    apply_route_a_stack_day,
    summarize_route_a_stack,
)

__all__ = ["RouteAStackParams", "apply_route_a_stack_day", "summarize_route_a_stack"]
