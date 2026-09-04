# Phase 4 round-2

Setup A′：普查、尺度卡、停損幾何、費用殺閘、**漏斗 + 限價成交率** 已落地。
規格在 `docs/ROADMAP_SMC_BACKTEST.md`（Setup A′：**費用殺閘已做；進場尚未收斂**）。
**不要勾 Phase 4。** CHoCH / impulse 尚未改 `decide()`。Smoke 與 funnel **不是 go/no-go**。

- [census/FINDINGS.md](census/FINDINGS.md) — detector vs join
- [census/SCALE_CARD.md](census/SCALE_CARD.md) — 費用／雜訊／結構三層
- [census/census.json](census/census.json) / [census/scale_card.json](census/scale_card.json)
- [smoke/SMOKE.md](smoke/SMOKE.md) / [smoke/smoke.json](smoke/smoke.json) — 高頻格 8 日,`2025-05-07`→`2025-09-16`
- [funnel/FUNNEL.md](funnel/FUNNEL.md) / [funnel/funnel.json](funnel/funnel.json) — IS 漏斗與 conservative 成交率
