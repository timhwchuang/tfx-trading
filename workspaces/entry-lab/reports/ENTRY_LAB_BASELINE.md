# Entry Lab Baseline

> Diagnostic only — not gate.

## Cross-thesis matrix

| slug | split | n | pct_w30_pos | exit_gap_med | tier |
|------|-------|---|-------------|--------------|------|
| gdc | train | 79 | 57.0 | 23.0 | descriptive_ci |
| gdc | valid | 15 | 66.7 | 53.71 | descriptive_only |
| gudt | train | 53 | 58.5 | 19.0 | descriptive_ci |
| gudt | valid | 11 | 72.7 | 49.0 | hypothesis_only |
| frp | train | 211 | 49.3 | 19.0 | descriptive_ci |
| frp | valid | 46 | 45.7 | 30.0 | descriptive_ci |
| sfbt | train | 229 | 51.1 | 15.5 | descriptive_ci |
| sfbt | valid | 52 | 57.7 | 25.66 | descriptive_ci |

## Paired GDC barrier vs GUDT trail (train)

- n_paired: 53
- delta_net_median: 0.0
- contract_flip_count: 1

## Filter intersection (exploratory)


### frp train filter Jaccard

```json
{
  "r2_with_trend": {
    "r2_with_trend": 1.0,
    "risk_unit_low": 0.0,
    "structure_long": 0.531
  },
  "risk_unit_low": {
    "r2_with_trend": 0.0,
    "risk_unit_low": null,
    "structure_long": 0.0
  },
  "structure_long": {
    "r2_with_trend": 0.531,
    "risk_unit_low": 0.0,
    "structure_long": 1.0
  }
}
```

### sfbt train filter Jaccard

```json
{
  "r2_with_trend": {
    "r2_with_trend": 1.0,
    "risk_unit_low": 0.122,
    "structure_long": 1.0
  },
  "risk_unit_low": {
    "r2_with_trend": 0.122,
    "risk_unit_low": 1.0,
    "structure_long": 0.122
  },
  "structure_long": {
    "r2_with_trend": 1.0,
    "risk_unit_low": 0.122,
    "structure_long": 1.0
  }
}
```

