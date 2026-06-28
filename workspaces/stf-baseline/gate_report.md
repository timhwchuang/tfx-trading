# FT-013 Gate Report — stf-baseline（Phase 0 · 結案）

> **Thesis P-007**：SuperTrend flip continuation — long-only Phase 0。  
> **Holdout**：v2.2.1 · train 2025 · valid 2026 Q1 · holdout 2026 Q2  
> **MUST-2**：FT-013 uses `entry_fill = entry_price + 1` before barrier — **gross 不可與 ORB/VSF raw entry 橫比**。

| 階段 | 結果 | 日期 |
|------|------|------|
| Phase 0a CF + tests | **完成** | 2026-06-28 |
| Phase 0b code review | **PASS**（agent MUST 對照） | 2026-06-28 |
| Phase 0c-1 Fingerprint | **未過** | 2026-06-28 |
| Phase 0c-2 Grid | **跳過**（§5.2 禁止） | — |
| Phase 1 Plugin | **不開** | — |

**結案碼**：`stf_fingerprint_fail` — train 2025 W30 stop-less gross median **−10.0**（n=67 ≥ 30）→ **MVPClosed**

---

## Phase 0b — Code review（MUST 對照）

| MUST | 結果 | 備註 |
|------|------|------|
| MUST-1 無 repaint | PASS | 僅已收 5m bar；`resample_1m_to_5m_closed` 排除 partial |
| MUST-1 確認 tick | PASS | Long `close > ST line`；Short 附錄 `close < ST line` |
| MUST-1 ATR | PASS | `atr_series_from_bars` SMA(TR)；索引 `bars[:idx+1]` 同 ORB |
| MUST-2 摩擦/滑價 | PASS | net=gross−5；Long entry_fill+1；`slippage_ratio_by_param` 產出 |
| MUST-3 long-only | PASS | flip_short 僅 post_entry appendix |
| MUST-3 cooldown | PASS | 5m bar 間隔 ≥ cooldown_bars |
| MUST-3 11:45/12:00 | PASS | **確認 tick** exchange time；`>= 11:45` 不 arm |
| §5.2 路徑分離 | PASS | `--fingerprint-only` / `--grid` 互斥 |

Review：**PASS** → 准許 0c train（2026-06-28）。

---

## Fingerprint (0c-1) — 凍結參數

`atr_period=10` · `st_mult=3.0` · `cooldown_bars=6` · `k_sl=1.0` · `tp_atr_k=2.0` · exit **`atr_barrier_180s`**

| 區間 | 產物 | W30 stop-less med | n | barrier gross/趟 | 判定 |
|------|------|-------------------|---|------------------|------|
| **Train 2025** | [`counterfactual_stf_fingerprint.json`](reports/counterfactual_stf_fingerprint.json) | **−10.0** | 67 | −2.36 / −7.36 net | **未過** |
| Valid 2026 Q1 | [`counterfactual_stf_valid.json`](reports/counterfactual_stf_valid.json) | +7.5 | 26 | +8.88 / +3.88 net | 參考 only（n<30） |

**0c-1 通過線**：n≥30 · W30 stop-less gross median **> 0** → train **未達**。

### Funnel（train · MUST-3）

`flip_long=113` → `cooldown_pass=113` → `window_pass=67` → `entry=67`

- 46 次 flip 在 **確認 tick 窗**（含 11:45 邊界）或無 confirm tick 被剔除
- 100% cooldown 通過（無 whipsaw 雙進在同日第二 flip 被 cooldown 擋下的 case 於 funnel 第二段）

### Slippage ratio（MUST-2）

- p50=**0.0336** · p90=0.04（1pt / ~29.8pt stop）→ **非** `execution_margin_thin`

---

## 進場後診斷（train fingerprint · 非 gate）

> stop-less forward 順向 ≠ net edge；不得用診斷結果回頭 tune train grid。

| 指標 | mean | median |
|------|------|--------|
| Barrier gross | −2.36 | −4.0 |
| 180s MFE / MAE | 13.49 / 16.42 | 7.0 / 15.0 |
| W5m stop-less gross | −3.55 | −5.0 |
| W15m stop-less gross | −6.91 | −2.0 |
| W30m stop-less gross | −14.33 | **−10.0** |

**Verdict**：`direction_failed` — W30 stop-less median 為負 → **順勢指紋失敗**（whipsaw / 翻轉後續非順向）

MAE median 15.0 ≥ MFE median 7.0 → 180s 內逆風路徑主導。

---

## Grid (0c-2)

**未執行** — §5.2 / SPEC §6：0c-1 未過 → **禁止** grid tune。

---

## Valid 2026 Q1（參考 · 不作 Phase 0 主判）

Valid 單季 barrier net 為正（med +9.5），W30 stop-less med **+7.5**，但 **n=26 < 30** 且 **train 方向指紋已負**。

**解讀**：與 ORB/VSF 族類似的小樣本 valid 正區間 — **不得**依 valid 回頭 tune 或復活 thesis（Playbook §2 valid 僅標 overfit_suspect 參考）。

---

## §Decision

| 欄位 | 值 |
|------|-----|
| **決策** | **MVPClosed** — `stf_fingerprint_fail`（0c-1 W30 median ≤ 0） |
| Grid | **跳過** |
| Plugin | **不開** |
| UAT | **維持** `strategy-vwap-momentum` |
| 下一提案 | queue **P-004 / P-006** continuation；skew 候選 **P-009** |
| 日期 | 2026-06-28 |
