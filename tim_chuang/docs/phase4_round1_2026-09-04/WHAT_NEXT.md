# What’s next（跨工作區延續說明）

> 給**下一位人類 reviewer**與**另一個工作區的 agent**：本文是 Setup A 第一輪 Phase 4 之後的延續契約。
> 聊天紀錄不保證可見；請以本目錄 + `ROADMAP_SMC_BACKTEST.md` 為準。

## 我們現在站在哪

- Setup A 第一輪正式掃描已完成 → **`verdict = no_go`**（`elected = null`）。
- 這是**假設被證偽**，不是基礎設施失敗；效能修（incremental FVG/SMC）已合進 `main`。
- **尚未**修改 `strategy/setup_a.py`；進度總覽的 **Phase 4 checkbox 仍不勾**。
- 本目錄保存可複核產物（`sweep/`、`blotter/`）與錯誤經驗（`LESSONS.md`）。

## 本 PR 請 reviewer／下一位 agent 讀什麼

1. `LESSONS.md` — 猜錯了什麼、硬數字、blotter 結論  
2. `sweep/gates.md` + `sweep/manifest.json` + `sweep/grid.csv`  
3. `blotter/trades_hi_freq_cons.csv` — 典型虧法（entry_stopped／stop）  
4. `ROADMAP_SMC_BACKTEST.md` 內「第一輪正式掃描結果／下一假設」段落  

**故意不做的事：** 不為過關降低 `MIN_IS_TRADES`；不把 RSI／VWAP 塞進同一張超大 grid；不上 live／不勾 Phase 5。

## 建議順序（契約）

### Step 0 — 本 PR review（現在）

人類另一位 reviewer 過目「錯誤經驗」是否寫得公允。合進 `main` 前以 review 意見為準。

### Step 1 — Merge 之後

Roadmap 中的下一假設成為正式文字。**仍不自動改策略 code**，直到人類點名要實作哪一刀。

### Step 2 — 下一刀實作（人類拍板；一次一個主軸）

| 優先 | 假設 | 要回答的問題 |
|---:|---|---|
| 1 | **收斂進場**（sweep／FVG 互動寫具體） | 漏斗能否別再 ~92% 死在 `no_sweep`？射頻有無機會靠近 ≥30 筆／IS？ |
| 2 | **波動感知停損／最小風險**（費用地板 + ATR 類） | 固定 3／5／8 點是否該淘汰？`entry_stopped`／−R 會否改善？ |
| 3 | **`entry_stopped` 明規則** | 同根進＋停要禁止、延後掛停，或風險≤費用則不進？ |
| 擱置 | `require_external` 當主力、RSI／VWAP／profile／footprint | 進場收斂後再各自開 Setup；external 本輪視為已知死路 |

流程：**先改 roadmap 細則 → 再改 code → pytest → 短區間 smoke → 正式 sweep（同一套硬閘）**。

### Step 3 — 再跑一輪 Phase 4

同一硬閘。仍可能 `no_go`（也是進度）。只有 `conservative` OOS 等門檻過了才談 Phase 5。

### Step 4 — 組合拳

SMC 進場站穩後，再獨立開 Setup B（例如 +VWAP 過濾），禁止與 A′ 參數全交叉塞同一張 grid。

## 給跨工作區 agent 的硬約束

1. 只動 `tim_chuang/`；當 `apps/`、`legacy/`、`tick_cache/`、根 `docs/AGENTS.md` 不存在。  
2. 改規則 **先改 roadmap 再改 code**。  
3. 不要為了製造 `go` 而放寬硬閘或調參作弊。  
4. 不要把本目錄的 `no_go` 產物當成「可 live」證據。  
5. Python ≥ 3.14；長 tape 只用 CLI，不要塞進 pytest。

## 人類下一步（checklist）

- [ ] Review／merge 本 PR  
- [ ] 拍板下一刀：進場收斂 / 波動停損 / entry_stopped 政策（選一或排序）  
- [ ] 開實作 PR（先文件細則，再 code）  
- [ ] 再跑正式 sweep，更新新一輪 `docs/phase4_round*_*/`
