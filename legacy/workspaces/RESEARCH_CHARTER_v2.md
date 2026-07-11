# RESEARCH Charter v2 — Dual-track era（SSOT）

```
ERA: Gen-2 dual-track (SessionBarCache + tick replay) · 2026-07+
STATUS: Active binding for alpha research guidance
NOT: Pilot authority · not UAT · not a license to trade live
DATA > narrative > archive epitaph
```

## 一句話

**Tick 回放與 SessionBar 研究並存；舊結論是 prior，不是死刑。**  
工具未到位或只差 filter/veto 時，**允許重測**——**數據才是真相**。  
失敗研究冷封存是為了**減少儀式誤導**，不是禁止你再問問題。

---

## 1. 誰讀什麼（AI / 人類）

| 必讀（活） | 勿當「這條路已死」的禁令 |
|------------|---------------------------|
| [`docs/AGENTS.md`](../docs/AGENTS.md) **§2** 安全護欄 | Archive 墓誌銘 / CORPSE 表 → **prior only** |
| 本 Charter + [`RESEARCH_LOG.md`](RESEARCH_LOG.md) | 舊 Playbook 全文儀式當唯一合法路徑 |
| 平台：`tick_cache` + SessionBarCache（見 §3） | 「FT-0xx MVPClosed = 永遠禁止重開」 |
| 現行 UAT 策略文件：GUDT Route A / Wash Beta | 為了給 AI 寫長 SPEC 才開工 |

**Agent MUST：**

- 用 Brief 寫清 **instrument**（tick / bar / both）與 **falsify**  
- 需要時**讀** archive 當背景；**不得**用 archive 阻擋人類要求的重測  
- 重測結果以 **emit→score / CF 數字** 為準，不以墓誌銘覆寫數據  

**Agent MUST NOT：**

- 把 `ARCHIVE/research-*` 當開案模板或 gate 神諭  
- 未經人類改 `simulation: false` / 真單路徑  

---

## 2. 真實場景約束（L0 — 物理，不棄用）

| 約束 | 含義 |
|------|------|
| qty=1 full flat | 無加碼 / 分批當系統假設 |
| 摩擦 ~5pt / RT | 報告要有 net 視角；path ≠ expectancy |
| 日盤 08:45–13:45 · 夜盤另契約 | 跨 session = 研究旗標，非默認 hold |
| bar close / next open = 代理 | Live = IOC/queue；CF 做排序與 falsify |
| 有 bar / tick 的日 = 可研究日 | disk SSOT；缺檔要先補 cache |
| UAT ≠ alpha | 引擎/對帳持續；不用 net 當 UAT 過關 |

---

## 3. 雙軌儀器（共存，不是取代）

| Track | 儀器 | 擅長 | 典型用途 |
|-------|------|------|----------|
| **A · Tick replay** | `tick_cache` + `BacktestEngine` / plugin / day_plans | 成交語意、狀態機、GUDT parity、執行摩擦近似 | L-edge→L-ops、UAT、與 live 同路徑驗證 |
| **B · SessionBar** | SessionBarCache / 1m→TF · timeline · path MAE/MFE | HTF regime、多 TF 結構、快速 census、emit→score | L-obs / L-path、filter·veto 掃描、故事成型 |

**規則：**

1. **兩軌都是一等公民**；Brief 必標 `instrument: tick | bar | both`。  
2. Bar 上 path 好看 **不自動** 等於 tick 上可交易；tick 過 gate **不自動** 證明 bar 結構假說。  
3. 理想路徑：`bar 成型 / 粗 filter` →（人類 Pick）→ `tick replay 確認` → UAT。  
4. 允許 **只跑 bar** 或 **只跑 tick** 做 falsify；結論必須標儀器。

### 3.1 基礎設施健康（研究前自檢）

| 層 | 狀態目標 | 入口 |
|----|----------|------|
| tick_cache / kbars | 研究窗內檔案齊 | `DATA_SPLIT` · `CACHE_AUDIT` · `storage.cache_audit` |
| SessionBarCache | day-session disk SSOT；overnight 可重建 | `storage/session_bar_cache.py` · storage SPEC |
| Tick backtest | plugin + MockBroker 可重跑 | trading-backtest · app sweep / baseline |
| Bar path lab | emit 候選 → MAE/MFE windows | `post_trigger_windows` · OSF/timeline helpers |
| Live bars（可選） | tick→1m 進 SessionBars | `LIVE_BARS` / live ingest |

**缺口時：先補工具或補資料，再擴大 thesis 結論**——不把「跑不起來」寫成「故事已死」。

---

## 4. Archive / 墓誌銘怎麼用（反「文件封死」）

| 正確 | 錯誤 |
|------|------|
| 「Gen-1 在 X 儀器、Y gate 失敗；可能是工具/出場/缺 filter」 | 「這族永遠不能研究」 |
| 重開時寫差在哪：新 filter、veto、session、instrument | 無視 prior、同一 knob 無限刷同一窗 |
| 新跑出數字 → 更新 Brief / LOG；墓誌銘可加註「retest」 | 用舊 gate_report 否決新數據 |

**人類一句「我想重測 X + filter Y」= 准許開工**（仍受 §2 安全護欄）。  
Agent **禁止**回答：「文件寫死了所以不能做。」

可重開的常見理由（鼓勵寫進 Brief）：

- 當時無 SessionBar / 夜盤契約不清  
- 只測 raw entry、未測 **關鍵 filter / veto**  
- exit 殺 edge（進場方向未 falsify）  
- n=0 或錨點錯（工具 bug）  

---

## 5. 產物階梯

```
L-obs   月誌 / regime / 故事草稿          (bar 優先)
L-path  機械 emit → path / 粗 filter      (bar 或 tick 標清)
L-edge  ≥2 窗 + 摩擦 + 一式出場           (建議 tick 或 both)
L-ops   plugin + UAT smoke + 人類 Pilot   (tick 路徑)
```

資源：同時 **Main ≤1** · **Scout ≤2**（Scout 可專門試 filter/veto）。

---

## 6. Stage 流程

| Stage | 做什麼 | 殺線（數據，不是墓誌銘） |
|-------|--------|--------------------------|
| **0** Brief | instrument · session · side · filter/veto 假設 · falsify | 寫不出 falsify → 不開工 |
| **1** Observe | 深讀 + 粗掃 | 無機械規則草稿 → 停 |
| **2** Path | emit→score；可測 **小 filter 組**（一輪內） | 本輪數據未過 soft bar → park **本輪**；可換儀器/假說再 Brief |
| **3** Edge | 兩段窗 + 一式 exit + net@5pt | n 過稀 / net 無意義 → kill 本 Brief |
| **4** Ops | 人類 Pick 後 plugin / UAT | Agent 禁止真單 |

**單月 / 單窗：** 禁止「調到過關」的無限 knob spam。  
**允許：** 新 filter 假設 → 新一輪 Brief（寫清與上一輪差異）→ 再跑。

**預設 split：** 探索/訓練偏 2025；OOS 偏 2026Q1（BRIEF 可覆寫）。  
Holdout 厚儀式 = optional；防偷看切分仍有效。

---

## 7. 新開案三行

1. **標清 instrument**（tick / bar / both）；缺工具或 cache 先補。  
2. **先出數字**（census / path / 小 CF），再決定要不要長 SPEC。  
3. **失敗寫墓誌銘 prior**；不累積「永禁」條款。人類可要求 retest。

---

## 8. 當前組合

| 槽 | 狀態 |
|----|------|
| **Main** | **空** — 人類指定；**不排除**重測舊故事 + 新 filter/veto |
| **UAT** | GUDT Route A / Wash Beta |
| **平台** | tick_cache · SessionBarCache · dual-track |
| **Archive** | 舊 FT 全文 / 儀式 — prior，**非 ban list** |

---

## 9. 週節奏 · 像交易自問

週一狀態 · 週中先契約 review 再長跑 · 週五 `RESEARCH_LOG`。

1. 13:30 還進得去嗎？  
2. 停損是結構錯還是太近？  
3. 夜盤空窗 path 怎麼算？  
4. bar 結論在 tick 上還在嗎（或相反）？  
5. 扣 5pt 後你願不願 qty=1 試兩週？  

---

## 10. Legacy 對照

| 舊誤導 | 現在 |
|--------|------|
| Playbook 全儀式 = 唯一合法 | 本 Charter + 短 Brief |
| MVPClosed = 永死 | prior；可 retest |
| 只有 bar 或只有 tick | **雙軌共存** |
| 文件否決研究 | **數據否決/通過研究** |

索引（考古）：[`docs/ARCHIVE/research-2026-h1/INDEX.md`](../docs/ARCHIVE/research-2026-h1/INDEX.md) · [`_archive/README.md`](_archive/README.md)
