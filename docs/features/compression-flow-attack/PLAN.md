---
id: FT-017
slug: compression-flow-attack
status: MVPClosed
closed: 2026-06-28
outcome: cfa_fingerprint_fail
thesis_class: skew
proposal_id: P-010
opened: 2026-06-28
phases: [0]
blockers: []
design_review: senior-trader 2026-06-28 — PASS (P0 sealed)
---

# FT-017 — Compression Flow Attack（PLAN）

> **Holdout**：v2.2.1 · train 2025 · valid 2026 Q1 · holdout 2026 Q2  
> **class**：**skew** · G3S n≥15 · §3.2  
> **封印 MUST**：[`SPEC.md`](SPEC.md) §5.1 · **診斷順序**：§5.2–§5.3

## Phase 0-design — SPEC/PLAN 審閱

- [x] SPEC + PLAN（本檔）
- [x] 資深 TXF 審閱 PASS → SPEC §8 · YAML `design_review`（2026-06-28）
- [x] P0 檢查：`exhaustion_vol` 未用作死魚 · `min_stop_pts=8` · 10:00–12:30 與 FT-016 錯開 · 封印 A/B
- [ ] P1（0b 前）：slippage {0,1,2} 診斷 · gate_report friction@7 / G-SK5

## Phase 0a — Counterfactual（不得跑 train）

- [x] `reporting/compression_flow_attack_counterfactual.py`（compress · quiet/attack · MUST-1–5 · funnel · post_entry · skew_gate）
- [x] `scripts/ft017_cfa_counterfactual.py`（`--fingerprint-only` · `--grid`）
- [x] `tests/reporting/test_compression_flow_attack_counterfactual.py`
- [ ] 對照 [`flow_flip_counterfactual.py`](../../../apps/trading-app/src/reporting/flow_flip_counterfactual.py)：`RollingFlowWindow` 語意一致
- [ ] 對照 [`volatility_baseline.py`](../../../apps/trading-app/src/reporting/volatility_baseline.py)：`atr_series_from_bars` ATR(20)

### 優先測試

| # | Case |
|---|------|
| 1 | `range_M >= compress_k×ATR` → 無 compress_pass |
| 2 | `ATR_ref >= atr_regime_cap × session_median` → 無 regime_pass |
| 3 | quiet 窗 `mean(vol_1s) > session p50` → 無 quiet_pass |
| 4 | attack 窗 buy_ratio 不足 · vol 不足 → 無 attack_signal |
| 5 | attack 成立但 `stop_dist < 8` → attack_signal 計、**無** entry |
| 6 | Long：tick chase · 結構 stop = max(1m low, 0.75×ATR) |
| 7 | Short：對稱 high |
| 8 | **10:00** 前 attack 窗起始 → 不 arm |
| 9 | attack 觸發 **≥ 12:30** → 不 arm |
| 10 | 第二筆 attack 同日 **忽略**（1 筆/日） |
| 11 | funnel 六階 + **絕對數** |
| 12 | exit `atr_barrier_900s` · payload 含 `post_entry_diagnosis_by_param` · `skew_gate_by_param` |
| 13 | `atr_compress_floor=10` 低波日仍可 compress（不受 min_atr=25 阻擋） |

## Phase 0b — Code review（MUST 先於 train）

- [x] Bugbot review（2026-06-28）— 5 findings 已修復 · 17 tests pass
- [ ] 人類 review PASS（可選複核）
- [ ] MUST-1 compress + regime + session ATR median
- [ ] MUST-2 quiet/attack 60s 窗分離 · ratio/vol 門檻
- [ ] MUST-3 tick entry · 結構 stop · min_stop_pts
- [ ] MUST-4 funnel 六階絕對數
- [ ] MUST-5 摩擦 5 · post_entry · skew_gate hook
- [ ] §5.2 fingerprint / grid 路徑分離

## Phase 0c — Train 2025（兩段 · 禁止跳步）

### 0c-1 Fingerprint（2026-06-28 · 完成）

**結果**：**`cfa_fingerprint_fail`** · n=**0** · W30 med **—** · **grid 跳過**

| 漏斗 | 絕對數 |
|------|--------|
| session_days | 241 |
| compress_pass | **0** |
| regime_pass | 233 |
| quiet_pass | 240 |
| attack_signal | 236 |
| entry | **0** |

**解讀**：attack 觸發日多，但 **signal_1m 同時 compress_pass 從未成立**（封印 A）— 壓縮與 flow 攻擊在 2025 train **不同步** · 非 min_stop 瓶頸。

### 0c-2 Grid（僅 fingerprint 過）

```bash
python scripts/ft017_cfa_counterfactual.py --cache-dir ../../../tick_cache --grid
```

Grid 組合：`compress_k` 3 × `atr_regime_cap` 2 × `attack_ratio_min` 3 × `min_stop_atr_k` 3 × `tp_atr_k` 3 = **162** combos

**未過** → `cfa_fingerprint_pass_g1_fail` / `cfa_no_skew_champion` / `cfa_train_no_go`

### CF 解讀預案（開跑前）

| Scenario | 意義 | outcome |
|----------|------|---------|
| compress 多 · attack 少 | vol_floor / ratio 太嚴 | funnel 註記 |
| attack 多 · W30 ≤ 0 | 假突破 / 追價方向錯 | `cfa_fingerprint_fail` |
| W30 > 0 · G1 fail | `direction_ok_margin_thin` / 摩擦 | `cfa_fingerprint_pass_g1_fail` |
| train 過 · valid ≤ 0 | overfit | `cfa_overfit_suspect` |
| `slippage_ratio_p50 > 0.2` | 執行空間薄 | `execution_margin_thin` 註記 |

## 產物（`workspaces/cfa-baseline/`）

| 檔案 | 內容 |
|------|------|
| `gate_report.md` | **`## Fingerprint (0c-1)`** · **`## Grid (0c-2)`** · **`## Valid 2026 Q1`** · §3.2 skew · post_entry · outcome code |
| `reports/counterfactual_cfa_fingerprint.json` | train 2025 單點 · funnel · post_entry · skew_gate |
| `reports/counterfactual_cfa_valid.json` | valid 2026 Q1 參考（0c-1 即產） |
| `reports/counterfactual_cfa_train.json` | grid（僅 0c-2） |

### gate_report 模板（CLI MUST 產出）

1. Phase 0b review 狀態（pending → PASS）
2. **Fingerprint (0c-1)**：W30 med · n · funnel **絕對數**（六階）· post_entry verdict · Long/Short 分欄
3. **Grid (0c-2)**：summary_by_param · best_passing · §3.2 disqualify · friction@7
4. **Valid 2026 Q1**：n · net · W30（參考 only）
5. **§Decision** + outcome code
6. 執行備註：tick chase · min_stop · Pilot IOC（非 0c gate）

## Phase 1 — Plugin

- [ ] `packages/strategies/compression-flow-attack/`（train 過 + 人類 Go 後）
