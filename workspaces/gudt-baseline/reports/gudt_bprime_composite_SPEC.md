# B′ Composite — distribution short (second leg)

## Long leg (B′)

- `flow_turn_ts < p0_ts` → flow_turn + drive_low_struct; else p0 + sealed
- V10 ft veto unchanged

## Entry vetoes (optional)

- **pre_break_br**: skip day if BR at `break_dh − 5min` < 0.35 (v4)
- **pre_break_br_p0_only**: veto p0 pick only; ft winners unaffected (v5)
- **p0_ext_open**: skip p0 chase if `(dh − open) / ATR` > threshold → fallback early ft
- **p0_sess_vwap**: skip p0 chase if `(entry − session_vwap) / ATR` > threshold
- **flip_min_ext_open**: distribution flip only when `(dh − open) / ATR` > threshold

## Short leg — distribution second leg

Anchor: **P0 entry + 10min**

```
signal = (px < p0_entry) AND (BR < 0.42)
action: exit long at signal_px; enter short at signal_px
short_stop = drive_high + 2.0
```

**Short-only mode**: no long; trade only when signal fires.

