## 進場後診斷（retrofit · 1.5 · 非 gate）

> stop-less forward 順向 ≠ net edge；不得用診斷結果回頭 tune train grid。

| 指標 | mean | median |
|------|------|--------|
| Barrier gross | 1.44 | -7.0 |
| 180s MFE / MAE | 22.9 / 13.89 | 18.0 / 17.0 |
| W5m stop-less gross | 1.32 | 4.0 (net med -1.0) |
| W15m stop-less gross | 0.25 | 0.0 (net med -5.0) |
| W30m stop-less gross | -1.31 | 1.5 (net med -3.5) |

**Verdict**: `direction_weak`

- W30 median 1.5 撐不過摩擦 5.0 點
- 180s 內 MFE median 18.0 > MAE 17.0（路徑曾順向）

### Long / Short

| side | n | barrier med | W30 med |
|---|---:|---:|---:|
| Long | 476 | -9.0 | -2.0 |
| Short | 426 | -7.0 | 7.0 |
