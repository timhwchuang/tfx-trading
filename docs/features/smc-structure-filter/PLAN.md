---
id: FT-002
slug: smc-structure-filter
status: Draft
opened: 2026-06-18
owner: human+agent
target: UAT
phases: [0, 1, 2, 3, 4, 5]
blockers: []
---

# FT-002 — SMC Structure Filter（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。Phase checkbox 隨 PR 更新。  
> 設計審閱：[`REVIEW.md`](REVIEW.md)（資深交易人員）。

## Scope

- kbars 1m → frozen SMC v0.1（§4 全條款）
- `StructureRefreshPort` + `structure_stale` + `RiskGate`
- `regime_allows_entry`（與 trend **互斥**）
- P6-SMC-CAL harness（三組 counterfactual + friction）
- 跨 package SPEC 併入（§9）

## Out of scope

- tick 開槍 / 出場邏輯
- Order Block
- order book / 五檔
- `simulation: false`
- 以 CAL-8 代替 Pilot Phase 5

## Dependencies

| 項目 | 狀態 |
|------|------|
| FT-001 audit | Landed |
| `KBARS_ARCHIVE=1` | UAT 期必開 |
| ≥5 日 kbar_cache | Phase 2+；不擋 Phase 1 |
| P6-1 trend（對照組） | 已有 |

---

## Phases

### Phase 0 — 開 ft（文件）

- [x] SPEC.md（v2 精煉：§4 寫死 + stale + sweep + gate 對齊）
- [x] PLAN.md（本檔）
- [x] REVIEW.md（資深交易人員 re-review）
- [x] README / DOC_MAP / TODO §P6-SMC-CAL / CHANGELOG

### Phase 1 — Frozen rules（零 kernel 改動）

**目標**：`structure_algo_version=1` 可單測、可離線重現；**不改** runtime 行為。

**實作**

- [ ] [`structure.py`](../../../packages/strategies/vwap-momentum/src/strategy_vwap_momentum/structure.py)
  - `filter_closed_bars_1m` / `resample_time_buckets`
  - `session_slice_bars`（§4.3）
  - `detect_swings_confirmed`（§4.5 lag）
  - `detect_fvg` + `mitigate_fvgs`（§4.7）
  - `detect_bos` / `detect_sweep`（§4.6 / §4.8）
  - `compute_structure` / `structure_allows_entry` / `regime_allows_entry`
- [ ] [`test_structure.py`](../../../packages/strategies/vwap-momentum/tests/test_structure.py) — **強制 edge cases**：

| 案例 | 驗證 |
|------|------|
| `test_fvg_full_mitigation` | low≤fvg_low 且 high≥fvg_high 才移除 |
| `test_fvg_partial_touch_not_mitigated` | 僅刺入 zone |
| `test_fvg_active_latest_same_side` | 多缺口取最新 |
| `test_swing_confirmation_lag` | L=2 時 pivot 延遲確認 |
| `test_bos_requires_confirmed_swing` | 未確認 swing 不觸發 BOS |
| `test_session_range_0845_reset` | range 不含前日 / 夜盤 |
| `test_gap_day_no_false_bos` | 開盤 gap |
| `test_incomplete_5m_bar_excluded` | no-lookahead |
| `test_level2_min_strength_zero_strictest` | 0.0 語意 |
| `test_regime_mutual_exclusion` | 兩 filter 同開 → 拒絕 |

- [ ] `__init__.py` export
- [ ] [`strategy-vwap-momentum/SPEC.md`](../../../packages/strategies/vwap-momentum/SPEC.md) — §SMC stub 連結本 ft

**驗收（Phase 1 閘門）**

- [ ] `bash scripts/run-all-tests.sh` 全綠
- [ ] **無** engine / app runtime 改動
- [ ] 文件：Phase 1 僅驗演算法；**不**構成 CAL-8 依據（SPEC §1）

### Phase 2 — Offline harness

**目標**：真實 kbar 上回答 structure vs trend vs 無濾網。

- [ ] [`structure_calibration.py`](../../../apps/trading-app/src/reporting/structure_calibration.py)
  - 讀 `kbar_cache/{code}_kbars_{date}.csv`
  - 逐決策點呼叫 `compute_structure(as_of_ts=...)`（**重算**，非讀 live 快取）
  - 輸出 `structure_events.csv` + `structure_armed_join.csv`
- [ ] armed join：UAT log `momentum_armed` → as-of structure + 30s forward conversion
- [ ] 三組 counterfactual 腳本 / 文件：
  1. 兩 filter false
  2. structure only
  3. trend only
- [ ] 報表：**veto 單 vs 放行單** friction-adjusted expectancy 分解
- [ ] CLI：`python -m reporting.structure_calibration_cli`

**驗收**

- [ ] ≥5 日 kbar_cache 可重現報表
- [ ] **決策閘**：無正 `delta_expectancy` → Phase 3 暫緩 + CAL-8 No-Go 建議

### Phase 3 — Engine 接線

**目標**：live/backtest 一致；filter off 行為不變。

| 檔案 | 變更 |
|------|------|
| [`side_effect_ports.py`](../../../packages/trading-engine/src/trading_engine/core/side_effect_ports.py) | `StructureRefreshPort`, `NullStructureRefreshPort` |
| [`types.py`](../../../packages/trading-engine/src/trading_engine/core/types.py) | `MarketSnapshot` + `RiskGate.structure_stale` |
| [`settings.py`](../../../packages/trading-engine/src/trading_engine/settings.py) | `structure_*` 欄位 |
| [`runtime_config.py`](../../../packages/trading-engine/src/trading_engine/core/runtime_config.py) | `SWEEP_FIELD_TO_CONST` + `_CONST_TO_SNAKE` + 互斥 in `apply_strategy_params` |
| [`indicators.py`](../../../packages/trading-engine/src/trading_engine/indicators.py) | structure 快取 + `last_structure_refresh` |
| [`engine.py`](../../../packages/trading-engine/src/trading_engine/engine.py) | `_is_structure_stale`, `_risk_gate`, `refresh_atr` 掛載 |
| [`structure_refresh.py`](../../../apps/trading-app/src/integrations/structure_refresh.py) | `used_long_lookback` 剝離（SPEC §4.3） |
| [`config.yaml`](../../../apps/trading-app/config/config.yaml) | 新欄位預設 false |
| [`config.py`](../../../apps/trading-app/src/config.py) | Settings + load 互斥 fail-fast |
| [`params.py`](../../../packages/strategies/vwap-momentum/src/strategy_vwap_momentum/params.py) | `structure_*` |
| backtest bootstrap / [`engine.py`](../../../packages/trading-backtest/src/trading_backtest/engine.py) | 注入 `StructureRefreshPort` |

**測試**

- [ ] `test_structure_stale_blocks_entry_allows_exit`（對照 `test_atr_stale_and_reconnect_guards.py`）
- [ ] filter off：現有 strategy / determinism 測試 **無差異**

**驗收**

- [ ] backtest smoke 通過
- [ ] `structure_filter_enabled=false` → 與 main 行為等價

### Phase 4 — Strategy + audit + sweep

- [ ] [`strategy.py`](../../../packages/strategies/vwap-momentum/src/strategy_vwap_momentum/strategy.py) — `regime_allows_entry`；`risk.structure_stale` 檢查；`structure_veto` audit；armed enrichment
- [ ] [`observability.py`](../../../apps/trading-app/src/observability.py) — `record_structure_veto`
- [ ] `uat_report` / reporting parse `structure_veto`
- [ ] [`param_sweep.py`](../../../apps/trading-app/src/sweep/param_sweep.py) — grid 互斥跳過
- [ ] determinism：filter on 3-run hash

**驗收**

- [ ] log 含 `structure_veto` + `structure_algo_version`
- [ ] 3-run determinism 通過

### Phase 5 — UAT + CAL-8 + Land

**P6-SMC-CAL**

- [ ] UAT ≥5 日（累積證據）
- [ ] harness + sweep 完整
- [ ] ≥3 structure_veto near-miss 人工審閱
- [ ] CAL-8 → [`WeeklyStatus.md`](../../WeeklyStatus.md)

**Land（SPEC §9 MUST）**

- [ ] [`apps/trading-app/SPEC.md`](../../../apps/trading-app/SPEC.md) §Integration contracts
- [ ] [`packages/trading-engine/SPEC.md`](../../../packages/trading-engine/SPEC.md)
- [ ] [`packages/strategies/vwap-momentum/SPEC.md`](../../../packages/strategies/vwap-momentum/SPEC.md) §SMC
- [ ] [`docs/AGENTS.md`](../../AGENTS.md) §3
- [ ] [`CHANGELOG.md`](../../../CHANGELOG.md)
- [ ] ft status → **Landed**

**Pilot 提醒（不取代 Phase 5）**

- [ ] 文件明確：CAL-8 Go 後若上 Pilot，仍須 [`uat/APP.md`](../../uat/APP.md) Phase 5（20 日 / 80 筆 / …）

---

## Acceptance（關閉 ft）

- [ ] SPEC §11 全勾
- [ ] `run-all-tests.sh` 全綠
- [ ] CAL-8 書面結論（Go 或 No-Go）
- [ ] §9 文件併入完成

## Risks（更新）

| 風險 | 緩解 |
|------|------|
| SMC 主觀空間 | §4 寫死；`structure_algo_version`；edge case 測試表 |
| overfitting | B-class only；三組 counterfactual |
| stale 未接線 | Phase 3 必測 entry block / exit allow |
| sweep 繞過互斥 | runtime_config + param_sweep 雙重約束 |
| 文件漂移 | §9 Land 清單強制三份 SPEC |
| UAT≠Pilot | §8.2 明寫兩層 gate |

## 協作（實作期）

| 角色 | 職責 |
|------|------|
| **Daily Reviewer** | CAL-8 簽核；≥3 near-miss；前 5 大虧損日（Phase 5 若上 Pilot） |
| **永豐 API Specialist** | kbars gap/volume/時間對齊；重連後 refresh 順序 |
| **Ops** | `KBARS_ARCHIVE=1`；structure_stale 實機演練 |
| **工程** | §9 跨 package 文件同步 |

## Land checklist

- [ ] app + engine + strategy SPEC 已更新
- [ ] AGENTS.md + TODO.md + CHANGELOG
- [ ] README board → Landed
- [ ] 本 PLAN 全 Phase 勾選

## 參考

- SPEC：[`SPEC.md`](SPEC.md)
- REVIEW：[`REVIEW.md`](REVIEW.md)