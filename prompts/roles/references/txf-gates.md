# tfx-trading — 交易視角 Gate 速查（Senior Trader Role 用）

> 工程護欄以 [`docs/AGENTS.md`](../../../docs/AGENTS.md) §2 為最高優先；本檔為**交易判斷**錨點。

## Gate 分層

| Gate | 驗什麼 | 文件 |
|------|--------|------|
| **Merge code** | 測試全綠 | `bash scripts/run-all-tests.sh` |
| **UAT** | 狀態機、對帳、audit 可解析；**不驗獲利** | [`docs/uat/APP.md`](../../../docs/uat/APP.md) Phase 0–4、[`docs/uat/KERNEL.md`](../../../docs/uat/KERNEL.md) |
| **Pilot** | 量化門檻 + 穩定性 + 人類簽核 | [`docs/uat/APP.md`](../../../docs/uat/APP.md) **Phase 5** |
| **Live / Phase 6** | Trend filter CAL-8、旗標校準 | [`docs/TODO.md`](../../../docs/TODO.md) §P6-1-CAL、vwap [`SPEC.md`](../../../packages/strategies/vwap-momentum/SPEC.md) §6.1 |

**UAT Ready ≠ Live Ready ≠ Pilot Ready** — 三層不可混用。

## Pilot Phase 5 硬門檻（摘要）

- 樣本：≥20 交易日 + 80 round-trip；最近 10 日 ≥35 筆
- Expectancy (net) 最近窗 > +0.35 點/筆
- Sharpe > 0.60
- Max DD 使用率 < 70% of `max_acceptable_mdd_points`
- 最近 10 日 Expectancy > +0.30、無連續 3 日大虧
- 過去 10 日 **零 Critical**
- 參數凍結 ≥10 交易日（git 證明）
- determinism hash 可重現

## 系統能力限制（評估策略時必提）

| 項目 | 現況 |
|------|------|
| 持倉 | **qty=1**、全倉進出；無 scale-in / partial exit | engine SPEC §4.2.1 |
| Trend filter | 預設 **false**；開啟需 CAL-8 人類簽核 | TODO §P6-1-CAL |
| 回測成交 | 啟發式 slippage；非 order book | backtest SPEC §9 |
| UAT KPI | 秒停損率等為 **Pilot 觀測**，非 UAT pass 條件 | AGENTS §4.1 |

## 協作角色 → Repo 映射

| 角色 | 對應 |
|------|------|
| **Ops** | [`docs/ops/WindowsOps.md`](../../../docs/ops/WindowsOps.md)、P4-13 斷線護欄、Telegram 實機驗收 |
| **永豐 API Specialist** | [`docs/uat/KERNEL.md`](../../../docs/uat/KERNEL.md)、[`docs/ops/LIVE_SAFETY.md`](../../../docs/ops/LIVE_SAFETY.md)、pending/order callback |
| **Daily Reviewer** | [`docs/WeeklyStatus.md`](../../../docs/WeeklyStatus.md)、`python -m reporting <log>`、`uat_report` KPI |

## 關鍵 audit 行

- `SIGNAL_AUDIT` / `FILL_AUDIT` / `DAILY_SUMMARY` — 見 app SPEC §Integration contracts
- Near-miss、秒停損率、Expectancy — `uat_report.py` / Phase 5 審核