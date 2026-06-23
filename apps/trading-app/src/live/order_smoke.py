"""Manual UAT smoke: Shioaji Buy/Sell IOC + order callback diagnostics.

Human-only (simulation). Do not run with simulation: false unless you accept real orders.

Usage (from apps/trading-app/src):
  DUMP_ORDER_EVENTS=1 python -m live.order_smoke
  DUMP_ORDER_EVENTS=1 python -m live.order_smoke --engine-only
  DUMP_ORDER_EVENTS=1 python -m live.order_smoke --raw-only --subscribe-trade

Environment: SJ_API_KEY, SJ_SEC_KEY; config simulation: true (default).
Optional: --price 47900 (skip snapshot); --wait 15 (seconds per leg).
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Any

_SMOKE_EPILOG = """\
Examples:
  DUMP_ORDER_EVENTS=1 python -m live.order_smoke
  python -m live.order_smoke --raw-only --wait 20
  python -m live.order_smoke --engine-only --action buy --price 47900

Phases:
  raw    — direct api.place_order + set_order_callback (isolates Shioaji)
  engine — TradingEngine place_order + kernel handle_order_event path
"""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UAT order smoke: Buy/Sell IOC with callback diagnostics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_SMOKE_EPILOG,
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Only run raw Shioaji place_order (no TradingEngine)",
    )
    parser.add_argument(
        "--engine-only",
        action="store_true",
        help="Only run TradingEngine place_order path",
    )
    parser.add_argument(
        "--subscribe-trade",
        action="store_true",
        help="Call api.subscribe_trade(futopt_account) after login (live path; test sim fix)",
    )
    parser.add_argument(
        "--action",
        choices=("buy", "sell", "roundtrip"),
        default="roundtrip",
        help="Which leg(s) to run in engine phase (default: roundtrip)",
    )
    parser.add_argument(
        "--price",
        type=float,
        default=0.0,
        help="Limit reference price; 0 = fetch snapshot",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=15.0,
        help="Seconds to wait for callbacks per leg (default: 15)",
    )
    parser.add_argument(
        "--slippage",
        type=int,
        default=3,
        help="IOC slippage points added to buy / subtracted from sell (default: 3)",
    )
    return parser.parse_args(argv)


def _collect_callbacks(api: Any) -> tuple[list[tuple[Any, Any]], threading.Event]:
    events: list[tuple[Any, Any]] = []
    done = threading.Event()

    def _cb(stat: Any, msg: Any) -> None:
        events.append((stat, msg))
        name = getattr(stat, "name", str(stat))
        trade_id = ""
        if isinstance(msg, dict):
            trade_id = str(msg.get("trade_id") or (msg.get("order") or {}).get("id") or "")
        print(f"[RAW_CB] stat={name} trade_id={trade_id!r} keys={list(msg.keys()) if isinstance(msg, dict) else type(msg)}")

    api.set_order_callback(_cb)
    return events, done


def _snapshot_price(api: Any, contract: Any) -> float:
    snaps = api.snapshots([contract])
    if not snaps:
        raise RuntimeError("snapshots() returned empty — pass --price manually")
    snap = snaps[0]
    for attr in ("close", "buy_price", "sell_price"):
        val = getattr(snap, attr, None)
        if val:
            return float(val)
    raise RuntimeError(f"Cannot read price from snapshot: {snap!r}")


def _build_futures_order(api: Any, *, action: str, qty: int, limit_price: float, account: Any):
    import shioaji as sj

    return sj.FuturesOrder(
        action=sj.Action.Buy if action == "Buy" else sj.Action.Sell,
        price=limit_price,
        quantity=qty,
        price_type=sj.FuturesPriceType.LMT,
        order_type=sj.OrderType.IOC,
        octype=sj.FuturesOCType.Auto,
        account=account,
    )


def _raw_leg(
    api: Any,
    contract: Any,
    account: Any,
    *,
    action: str,
    ref_price: float,
    slippage: int,
    wait_sec: float,
    events: list[tuple[Any, Any]],
) -> str:
    limit = ref_price + slippage if action == "Buy" else ref_price - slippage
    order = _build_futures_order(
        api, action=action, qty=1, limit_price=limit, account=account
    )
    before = len(events)
    trade = api.place_order(contract, order, timeout=0)
    oid = str(getattr(getattr(trade, "order", None), "id", "") or "")
    print(f"[RAW] place_order {action} @ {limit:.1f} | trade.order.id={oid!r}")
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        time.sleep(0.25)
        if len(events) > before:
            break
    new_events = events[before:]
    print(f"[RAW] {action} leg: {len(new_events)} callback(s) in {wait_sec:.0f}s")
    return oid


def _run_raw_phase(api: Any, contract: Any, account: Any, args: argparse.Namespace) -> int:
    events, _ = _collect_callbacks(api)
    ref = args.price or _snapshot_price(api, contract)
    print(f"[RAW] ref_price={ref:.1f}")

    actions: list[str]
    if args.action == "roundtrip":
        actions = ["Buy", "Sell"]
    else:
        actions = ["Buy" if args.action == "buy" else "Sell"]

    rc = 0
    for action in actions:
        before = len(events)
        oid = _raw_leg(
            api,
            contract,
            account,
            action=action,
            ref_price=ref,
            slippage=args.slippage,
            wait_sec=args.wait,
            events=events,
        )
        if not oid:
            print(f"[RAW] WARN: empty order_id after place_order ({action})")
            rc = 1
        new_count = len(events) - before
        if new_count == 0:
            print(
                "[RAW] FAIL: no order callback — check subscribe_trade, session hours, "
                "and DUMP_ORDER_EVENTS=1 on engine path"
            )
            rc = 1
    print(f"[RAW] total callbacks: {len(events)}")
    return rc


def _wait_engine_pending(engine: Any, wait_sec: float) -> None:
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        snap = engine.get_state_snapshot()
        if not snap.is_pending:
            print(
                f"[ENGINE] pending cleared | qty={snap.position_qty} dir={snap.position_dir}"
            )
            return
        time.sleep(0.25)
    snap = engine.get_state_snapshot()
    print(
        f"[ENGINE] TIMEOUT still pending={snap.is_pending} "
        f"order_id={getattr(engine, 'pending_order_id', '')!r}"
    )


def _engine_leg(
    engine: Any,
    *,
    action: str,
    intent: str,
    ref_price: float,
    signal_id: str,
    exchange_ts: int,
) -> None:
    from trading_engine.core.types import OrderSignal

    sig = OrderSignal(action, 1, ref_price, intent, exchange_ts=exchange_ts, signal_id=signal_id)
    if not engine._validate_order_signal(sig):
        print(f"[ENGINE] signal rejected: {action} {intent}")
        return
    engine._arm_pending(sig)
    engine.place_order(sig)


def _run_engine_phase(engine: Any, args: argparse.Namespace) -> int:
    from trading_engine.adapters.shioaji_live import ShioajiLiveBootstrap

    ShioajiLiveBootstrap(engine).wire_live()
    engine._start_order_worker()

    ref = args.price or _snapshot_price(engine.api, engine.contract)
    print(f"[ENGINE] ref_price={ref:.1f} simulation={engine._cfg.simulation}")

    ts = int(time.time())
    rc = 0

    if args.action in ("roundtrip", "buy"):
        _engine_leg(
            engine,
            action="Buy",
            intent="entry",
            ref_price=ref,
            signal_id=f"smoke-{ts}-buy",
            exchange_ts=ts,
        )
        _wait_engine_pending(engine, args.wait)
        snap = engine.get_state_snapshot()
        if snap.is_pending:
            rc = 1
        elif snap.position_qty != 1:
            print(f"[ENGINE] WARN: expected Long 1 after buy, got qty={snap.position_qty}")

    if args.action in ("roundtrip", "sell"):
        snap = engine.get_state_snapshot()
        if snap.position_qty <= 0 and args.action == "roundtrip":
            print("[ENGINE] skip sell — no position (buy may have failed or IOC cancelled)")
        else:
            sell_action = "Sell" if snap.position_dir == "Long" else "Buy"
            intent = "exit" if snap.position_qty > 0 else "entry"
            _engine_leg(
                engine,
                action=sell_action,
                intent=intent,
                ref_price=ref,
                signal_id=f"smoke-{ts}-sell",
                exchange_ts=ts + 1,
            )
            _wait_engine_pending(engine, args.wait)
            if engine.get_state_snapshot().is_pending:
                rc = 1

    final = engine.get_state_snapshot()
    print(
        f"[ENGINE] final | pending={final.is_pending} qty={final.position_qty} "
        f"dir={final.position_dir} block_entry={final.block_new_entry}"
    )
    return rc


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.raw_only and args.engine_only:
        print("Choose at most one of --raw-only / --engine-only", file=sys.stderr)
        return 2

    import shioaji as sj

    from config import API_KEY, SECRET_KEY, SIMULATION, settings
    from core.runtime_config import default_runtime_config
    from integrations.engine_wiring import trading_app_engine_ports
    from trading_engine.engine import TradingEngine
    from trading_engine.testing.helpers import StubStrategy

    if not SIMULATION:
        print("Refusing to run: config simulation is false (live mode).", file=sys.stderr)
        return 2

    cfg = default_runtime_config()
    api = sj.Shioaji(simulation=True)
    api.login(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        subscribe_trade=True,
    )
    account = api.futopt_account
    if account is None:
        print("No futopt_account after login", file=sys.stderr)
        return 1

    code = settings.product_code
    category = code[:3]
    cat = getattr(api.Contracts.Futures, category, None)
    contract = getattr(cat, code) if cat is not None and hasattr(cat, code) else api.Contracts.Futures[code]
    print(f"Login OK | contract={code} simulation=True account={getattr(account, 'account_id', 'N/A')}")

    if args.subscribe_trade:
        api.subscribe_trade(account)
        print("[DIAG] called api.subscribe_trade(futopt_account)")

    run_raw = not args.engine_only
    run_engine = not args.raw_only
    rc = 0

    if run_raw:
        rc = max(rc, _run_raw_phase(api, contract, account, args))

    if run_engine:
        ports = trading_app_engine_ports(api=api, use_mock_adapter=False, with_alerts=True, runtime_config=cfg)
        engine = TradingEngine(
            api=api,
            strategy=StubStrategy(),
            **{k: v for k, v in ports.items() if k != "obs"},
        )
        engine.contract = contract
        engine.sync_positions(force_resync=True)
        rc = max(rc, _run_engine_phase(engine, args))
        try:
            api.logout()
        except Exception:
            pass

    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
