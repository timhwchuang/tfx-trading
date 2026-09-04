# 這條路不通 — 給下一位（Setup A / A′）

> 聊天紀錄不保證可見。請先讀
> [CLOSED.md](../phase4_round2_2026-09-04/CLOSED.md)
> 與 `ROADMAP_SMC_BACKTEST.md`。
> 本目錄是第一輪 `no_go` 產物，不是「再掃一次」的許可。

**日盤 sweep → event → 回踩 FVG 選不出 plateau。**  
不要開 A′ 3b、不要改 `decide()` 養樣本、不要跑第二輪 `sweep.py`、不要勾 Phase 4、不上 live。

## 我們現在站在哪

- Setup A 第一輪正式掃描 → **`verdict = no_go`**（`elected = null`）。產物在本目錄。
- PR #7 已合進 `main`。獨立 review 修正了死因排序。
- A′ 停損幾何與費用殺閘已落地；普查、尺度卡、smoke、漏斗已完成。
- 漏斗：same+next FVG = **0**；nested unique **17** < 30。這條路不通。
- `setup_a.py` 維持幾何 + 費用殺閘；那不是 elect。

## 請讀什麼

1. [CLOSED.md](../phase4_round2_2026-09-04/CLOSED.md) — **這條路不通**
2. `ROADMAP_SMC_BACKTEST.md` — Phase 4 文首同一句
3. [orb_day_2026-09-04/README.md](../orb_day_2026-09-04/README.md) — **下一條測量（日盤 ORB）**
4. `docs/TMF_DESK_CARD.md` — 下一條 setup 仍要的尺子
5. 本目錄 `LESSONS.md` + `sweep/` + `blotter/` — 第一輪事實
6. `docs/phase4_round2_2026-09-04/census/` — 普查 + 尺度卡
7. `docs/phase4_round2_2026-09-04/smoke/` — 一格 smoke（不是 elect）
8. `docs/phase4_round2_2026-09-04/funnel/` — 漏斗數字

**禁止：** 降低 `MIN_IS_TRADES`；停損晚一棒；RSI／VWAP 塞進 A′；把 `min_r=15` 或 `buffer∈{3,5,8}` 當微台尺度；為救 17 去改 CHoCH / impulse。

## A′ 已走完（不要重做）

普查 → 停損幾何 → 費用殺閘 + smoke → 漏斗。3b **不做**。第二輪主掃描 **取消**。

## 下一條

日盤 **ORB**（測量，不是 elect）：[orb_day_2026-09-04/README.md](../orb_day_2026-09-04/README.md)。  
Setup B（`taken` 延續）仍停放：先日盤普查，先改 roadmap，再另開 plan。不是 A′ 延到 15:05。不要開第二份 roadmap。

## 給跨工作區 agent 的硬約束

1. 只動 `tim_chuang/`；當 `apps/`、`legacy/`、`tick_cache/`、根 `docs/AGENTS.md` 不存在。
2. 改規則 **先改 roadmap 再改 code**。A′ 這條路不通；下一刀是日盤 ORB 測量，不是 3b、不是 A′ grid、不是立刻 Setup B。
3. 不要為了製造 `go` 而放寬硬閘或調參作弊。
4. 不要把本目錄的 `no_go` 產物當成「可 live」證據。
5. Python ≥ 3.14；長 tape 只用 CLI，不要塞進 pytest。
6. 不要開第二份 roadmap。

## 人類下一步（checklist）

- [x] Review／merge 第一輪 no_go PR
- [x] 普查 + 尺度卡 + desk card
- [x] 停損幾何 + 費用殺閘 + smoke + 漏斗
- [x] A′ 日盤 elect 宣告不通（CLOSED.md）
- [ ] 日盤 ORB：`setup_orb.py` + conservative `2025-06-02`→`2025-08-29`（進場=**追價停損單**；見 orb_day README；不是 elect）
- [ ] Setup B `taken` 延續：日盤普查（獨立 setup；停放，尚未開 plan）
