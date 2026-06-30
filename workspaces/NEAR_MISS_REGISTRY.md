# Near-Miss Registry — Alpha train 正帳面 / 次級 gate 未過

> **更新**：2026-06-30 · 工具：`python -m scripts.build_near_miss_registry`
> **禁止**依本表自動 tune grid；僅供 Pick thesis / closure_review 參考。
> SSOT：[`OUTCOME_REGISTRY.md`](../docs/features/ai-backtest-tuning/OUTCOME_REGISTRY.md)

| FT | train net_total | n | net/趟 | outcome_class | 可申訴 | TXF 備註 |
|----|----------------:|--:|-------:|---------------|:------:|----------|
| FT-018 | 173.9 | 53 | 3.28 | `skew_profile_fail` | 是 | TXF 2026-06-30：near-miss 標竿 · closure_review passed · 非 champion |
| FT-014 | 133.0 | 7 | 19.00 | `sample_sparse` | 否 | n=7 · phase0 未過 · 可申訴否 |

## 手動補充（審計標註）

| FT | 備註 |
|----|------|
| FT-006 k=2.5 | 事後 k 切片 · net_total +162.2 · **非** pre-register · 禁止救屍 |
| FT-009 ORB | legacy 01–04 過 · 2025 全 param net 負 · 非 near-miss |
