"""Shared order-pipeline constants."""

# P0-5: exit reasons that are hard/loss stops and therefore MUST get out
# (escalate a missed IOC to a market order). Profit-taking / trailing exits
# are not urgent and keep their limit-IOC retry semantics.
_STOP_LOSS_REASONS = frozenset({"stop_loss", "stop_loss_vwap"})

__all__ = ["_STOP_LOSS_REASONS"]
