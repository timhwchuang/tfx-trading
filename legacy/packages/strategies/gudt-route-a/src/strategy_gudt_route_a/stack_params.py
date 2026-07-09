"""Map GudtRouteAParams to RouteAStackParams for CF / replay."""

from __future__ import annotations

from strategy_gudt_route_a.params import GudtRouteAParams
from strategy_gudt_route_a.route_a_exit import RouteAParams
from strategy_gudt_route_a.stack import RouteAStackParams
from strategy_gudt_route_a.wash_bridge import BPrimeCompositeParams, DistributionHedgeParams


def stack_params_from_gudt(params: GudtRouteAParams) -> RouteAStackParams:
    ext = params.extension_exit
    if ext not in ("trail", "ema3", "ema5", "ema_either", "ema_both", "trail_or_ema_either"):
        ext = "ema5"
    return RouteAStackParams(
        route_a=RouteAParams(extension_exit=ext),  # type: ignore[arg-type]
        br5=BPrimeCompositeParams(
            pre_break_br_min=params.pre_break_br_min,
            pre_break_br_p0_only=True,
            p0_ext_open_max=params.p0_ext_open_max,
            flip_min_ext_open=params.flip_min_ext_open,
            distribution=DistributionHedgeParams(
                confirm_sec=120,
                confirm_min_dump_atr=params.confirm_min_dump_atr,
                confirm_slope2_min=params.confirm_slope2_min,
                confirm_slope2_max=params.confirm_slope2_max,
            ),
        ),
    )
