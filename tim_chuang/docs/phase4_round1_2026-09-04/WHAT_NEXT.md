# What’s next（跨工作區延續說明）

> 給**下一位人類 reviewer**與**另一個工作區的 agent**。
> 聊天紀錄不保證可見；請以 `ROADMAP_SMC_BACKTEST.md` 的 **Setup A′** 與 [TMF_DESK_CARD.md](../../TMF_DESK_CARD.md) 為準。
> 本目錄是第一輪 `no_go` 產物；契約已更新，下面舊的「先收斂進場／晚一棒掛停」**作廢**。

## 我們現在站在哪

- Setup A 第一輪正式掃描 → **`verdict = no_go`**（`elected = null`）。產物在本目錄。
- PR #7 已合進 `main`。獨立 review 修正了死因排序；細則寫進 roadmap Setup A′。
- `setup_a.py` 停損幾何與費用殺閘已落地（sweep 極值 ± 墊片;`min_r_points=15` 不 arm）;**Phase 4 checkbox 仍不勾**;不上 live。
- 費用殺閘 + conservative smoke **已完成**。載入 `2025-05-07`→`2025-09-16`(不是 20 個孤立日)。產物:`docs/phase4_round2_2026-09-04/smoke/`。沒有尺度卡不准開 grid。

## 請讀什麼

1. `ROADMAP_SMC_BACKTEST.md` — **Setup A′**
2. `docs/TMF_DESK_CARD.md` — 寫 decide() 前的合約／費用／時段／成交假設
3. 本目錄 `LESSONS.md` + `sweep/` + `blotter/` — 第一輪事實
4. `docs/phase4_round2_2026-09-04/census/` — 普查 + 尺度卡
5. `docs/phase4_round2_2026-09-04/smoke/` — Step 2 一格 conservative smoke(**不是 go/no-go**)

**故意不做的事：** 不降低 `MIN_IS_TRADES`；不停損晚一棒掛；不把 RSI／VWAP 塞進 A′ grid；不上 live／不勾 Phase 5；**不准把 `min_r=15` 或 `buffer∈{3,5,8}` 當成已量過的微台尺度**。

## 建議順序（契約）

### Step 0 — 指標普查 + 尺度卡（已完成；不改策略）

產物在 `docs/phase4_round2_2026-09-04/census/`。重跑：

```bash
cd tim_chuang
.venv/bin/python -m tfx_trading.backtest.census \
  --start 2025-03-03 --end 2025-11-06 \
  --out docs/phase4_round2_2026-09-04/census
.venv/bin/python -m tfx_trading.backtest.scale_card \
  --start 2025-03-03 --end 2025-11-06 \
  --out docs/phase4_round2_2026-09-04/census
```

### Step 1 — 停損幾何（已完成）

拿掉「取較近者」。停損 = sweep 那根 5m 的 high/low ± 墊片。進 FVG top 不得 `top±buffer`。
單元測試：空／多各一則，`R != stop_buffer`。**禁止**晚一棒掛停。

### Step 2 — 費用殺閘 + smoke（已完成）

`min_r_points` / `r_below_floor`:R ≤ 來回費用不 arm。預設 15 只殺費用地板,不是雜訊地板。
驗證:8 個 v1 高頻格日曆日;連續載入 `2025-05-07`→`2025-09-16`(PDH / `prev_night`)。
重跑:

```bash
cd tim_chuang
.venv/bin/python -m tfx_trading.backtest.smoke
```

產物:`docs/phase4_round2_2026-09-04/smoke/`。**不是 go/no-go**;n≪30 是預期。下一步仍是進場收斂(漏斗看完才動)。

### Step 3 — 進場收斂（漏斗與成交率看完才動）

確認改 CHoCH；FVG 落在 sweep impulse。然後才談第二輪主掃描
（conservative only；拿掉 `max_hold` 與 `require_external`；多空 × 多頭／震盪分開報）。

### Step 4 — 再跑一輪 Phase 4

同一硬閘。仍可能 `no_go`。過了才談 Phase 5。

### Step 5 — 組合拳

A′ 站穩後再獨立開 Setup B。禁止與 A′ 全交叉。

## 給跨工作區 agent 的硬約束

1. 只動 `tim_chuang/`；當 `apps/`、`legacy/`、`tick_cache/`、根 `docs/AGENTS.md` 不存在。
2. 改規則 **先改 roadmap 再改 code**。Setup A′ 停損幾何與費用殺閘已落地;策略下一刀是 Step 3(進場收斂;漏斗看完才動)。
3. 不要為了製造 `go` 而放寬硬閘或調參作弊。
4. 不要把本目錄的 `no_go` 產物當成「可 live」證據。
5. Python ≥ 3.14；長 tape 只用 CLI，不要塞進 pytest。
6. 不要開第二份 roadmap。

## 人類下一步（checklist）

- [x] Review／merge 第一輪 no_go PR
- [x] 拍板：普查 → 停損／min R → 不晚掛 → 再收斂進場（寫進 Setup A′）
- [x] 跑 IS 指標普查 + 尺度卡（`census/`、`SCALE_CARD.md`）
- [x] 寫 `TMF_DESK_CARD.md`（合約／費用／時段；寫 `decide()` 前硬閘）
- [x] 停損幾何：sweep 極值 ± 墊片（不是再掃 3/5/8 當 R）
- [x] 費用殺閘 + 8 日 / `2025-05-07`→`2025-09-16` smoke(含 13:40 vs 2R)
- [ ] 再跑正式 sweep，更新新一輪 `docs/phase4_round*_*/`
