"""Parameter sweep, determinism gate, and Pilot readiness checks.

Import submodules directly (e.g. ``from sweep.param_sweep import sweep``) to avoid
eager ``backtest.engine`` loads via package ``__init__``.
"""

__all__ = [
    "capture_backtest_log_lines",
    "evaluate_pilot_gate",
    "format_pilot_gate_report",
    "run_hash",
    "sweep",
    "valid_score",
]
