---
id: FT-021
slug: gudt-route-a
status: Draft
opened: 2026-06-30
owner: human+agent
target: UAT
stable_contract: packages/strategies/gudt-route-a/SPEC.md
audit_schema_version: 1
---

# FT-021 — GUDT Route A UAT Stack（Plugin）

> **SPEC** = 將 FT-018b Route A UAT stack 從 reporting 研究層提升為 `strategy-gudt-route-a` plugin。  
> **不取代** [`SEAL_FT018b_B_PRIME.md`](../../../workspaces/gudt-baseline/SEAL_FT018b_B_PRIME.md) 或 [`gate_report.md`](../../../workspaces/gudt-baseline/gate_report.md)。

## 1. Summary

**問題**：Route A + br5 + 5m EMA extension + distribution structural confirm flip 僅在 counterfactual / probe 層驗證（[`ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md)），未接入 TradingEngine。

**目標**：`packages/strategies/gudt-route-a`（entry `gudt_route_a`）+ kernel backtest 對帳 counterfactual 觀察。

**使用者**：`workspaces/gudt-route-a-baseline`；UAT 候選，非 live 切換直至 parity 過關 + 人類 Go。

## 2. 策略契約（v1 = UAT stack，pre-registered）

### Leg 1 — Route A long

| 欄位 | 值 |
|------|-----|
| Router | B′ + **br5 p0-only** veto（`pre_break_br < 0.35` → skip p0，fallback ft） |
| p0 預設 | sealed 15m + BE + TP3 |
| Checkpoint | `ext_open > 5` AND 15m `gross > 0` |
| Extension | 60m、**no BE**、**5m EMA9>EMA21 break** |
| ft | `drive_low_struct` 不變 |

### Leg 2 — Distribution short overlay

| 欄位 | 值 |
|------|-----|
| Gate | `ext_open > 5` |
| Signal | P0+10m：`px < p0_entry` AND `BR < 0.42` → exit long |
| Confirm | P0+12m：`dump_atr ≤ −0.65` AND `−0.35 ≤ slope2 ≤ 0` |
| Short | entry @ confirm_px，stop `drive_high + 2`，hold 60m |

研究 SSOT：[`ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md)。

## 3. Out of scope v1

- 改 B′ sealed 參數或 br5 門檻 tune
- addon re-entry after 15m exit
- live UAT / pilot 切換
- 覆寫 FT-018 `gate_report.md` champion

## 4. Parity gates（kernel vs counterfactual）

對帳期間：**2025-05-01 .. 2026-06-30**，br5 router，stack = Route A + EMA5 + structural confirm。

| 指標 | Counterfactual 基準 | 允許偏差 |
|------|---------------------|----------|
| Full net | **+683** | ±15 pts |
| H1 (2025-05..10) | **+236** | 不得劣於 br5 baseline H1 |
| UAT 2m (2026-05..06) | **−106**（vs br5 −412） | 方向一致（優於 br5） |
| `extend_days` | **4** | 完全一致 |
| `flip_days` | **1**（6/29） | 決策日一致；PnL 單日 ±5 pts |
| confirm veto | 6/25 bounce 等 | 決策一致（不開空） |

逐日產出 `parity_report.json`：比對 `route`、`extend`、`flip`、`confirm_veto`、`net_pts`。

## 5. Definition of Done

- [ ] `docs/features/gudt-route-a/SPEC.md` + `PLAN.md` + board 列
- [ ] `strategy-gudt-route-a` 可 `pip install -e` + entry point 註冊
- [ ] `load_named_strategy("gudt_route_a", ...)` 可用
- [ ] `ft021_run_baseline.py` + `workspaces/gudt-route-a-baseline/`
- [ ] Parity harness 全綠（§4）
- [ ] `bash scripts/run-all-tests.sh` 全綠
- [ ] Bugbot ≤3 輪無未解 Critical/High；whack-a-mole → `REVIEW.md` 停等人類

## 6. 參考

- PLAN：[`PLAN.md`](PLAN.md)
- 研究：[`ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md)
- FT-018：[`gap-up-drive-trail/SPEC.md`](../gap-up-drive-trail/SPEC.md)
- Package：[`packages/strategies/gudt-route-a/SPEC.md`](../../../packages/strategies/gudt-route-a/SPEC.md)
