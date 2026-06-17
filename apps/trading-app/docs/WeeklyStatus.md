# Weekly Status — 人機協作開發日記

> 給**人類**看的進度、Follow-up、待決策。工程路線圖見 [`TODO.md`](../TODO.md)；文件職責見 [`docs/DOC_MAP.md`](../../../docs/DOC_MAP.md)。  
> **歷史週報**（2026-06-12～06-16）→ [`ARCHIVE/weekly-status-2026.md`](ARCHIVE/weekly-status-2026.md)

**用法**：重大決策時在下方新增一節（最新放最上面）。

---

## 範本（複製用）

```markdown
### YYYY-MM-DD（週次 / 標題一句話）

**目前進度**
- 

**人類必做（Follow-up）**
- [ ] 

**Pending / 待決策**
- 

**備註 / 開發日記**
- 
```

---

### 2026-06-17（Monorepo 遷移完成 + 文件/Windows 路徑對齊）

**目前進度**
- **`timhwchuang/tfx-trading`** monorepo 已上線；tag `v0.3.0-monorepo`；CI 綠燈。
- 路徑：`packages/trading-engine`、`packages/trading-backtest`、`packages/strategies/vwap-momentum`、`apps/trading-app`。
- 整合文件：[`SPEC.md`](../../../SPEC.md)、[`docs/Architecture.md`](../../../docs/Architecture.md)、[`docs/DOC_MAP.md`](../../../docs/DOC_MAP.md)。
- Windows 預設：`C:\tfx-trading`（venv 在 repo 根）；live 從 `apps\trading-app\src`。
- 舊四 repo README 封存橫幅已 push；**Archive 操作由人類在 GitHub 完成**。

**人類必做（Follow-up）**
- [x] 兩台電腦改 `git clone git@github.com:timhwchuang/tfx-trading.git`
- [ ] Windows UAT 機：clone 至 `C:\tfx-trading` → `bash scripts/setup-dev.sh`（或手動 venv + editable install）
- [ ] 舊四 repo GitHub **Archive**（Settings → Archive）
- [ ] UAT B3b：斷網暖機 / 有倉 CRITICAL（P4-13）

**備註**
- 安裝：`bash scripts/setup-dev.sh`；全測：`bash scripts/run-all-tests.sh`。
- 舊 `UPGRADE_RUNBOOK.md` 已 deprecated。

---

## 長期提醒（跨週有效）

| 項目 | 說明 |
| ---- | ---- |
| **Monorepo** | [`tfx-trading`](https://github.com/timhwchuang/tfx-trading) — `bash scripts/setup-dev.sh`；見 [`SPEC.md`](../../../SPEC.md) |
| **申請永豐 API** | 目前 **0 權限**。模擬 UAT：行情 + 帳務 + 交易（不需 CA）。 |
| **UAT 累積 tick** | `TICK_ARCHIVE=1` 每日落盤 → repo 根 `tick_cache/`。 |
| **KBARS_ARCHIVE** | 建議 UAT 一併開啟，供 ATR / 趨勢回測熱身。 |
| **Phase 3 UAT** | 可開跑（待 API）→ [`UAT_CHECKLIST.md`](UAT_CHECKLIST.md) + [`packages/trading-engine/docs/UAT_CHECKLIST.md`](../../../packages/trading-engine/docs/UAT_CHECKLIST.md) |
| **Phase 6 CAL B 類** | 待 UAT tick；見 [`packages/strategies/vwap-momentum/docs/CALIBRATION.md`](../../../packages/strategies/vwap-momentum/docs/CALIBRATION.md) |
| **Pilot 門檻** | UAT 全過 + CA；秒停損率硬指標 → [`BeforePilot.md`](BeforePilot.md) |
| **文件分層** | 架構 → [`docs/Architecture.md`](../../../docs/Architecture.md)；週報 → 本檔；可開工 → `TODO.md` |

---

### 2026-06-17（P0/P4-13 落地 + v0.2.2 發布）

> *（遷移前四-repo 紀錄；現行開發在 `tfx-trading` monorepo。）*

**目前進度**
- **P0 `atr_stale`** + **P4-13** 已實作：engine v0.2.2、strategy v0.1.2、app v0.1.2。
- 暖機：重連後**首筆 tick** 起算。

**人類必做（Follow-up）**
- [ ] UAT B3b（見上節）

---

### 2026-06-17（資料流釐清 + P6-1 暫緩 + Nautilus 借鏡）

**目前進度**
- Live 熱路徑在記憶體；`TICK_ARCHIVE=1` 非同步落盤；策略只吃 `MarketSnapshot`。
- **P6-1**：維持 `trend_filter_enabled: false`；UAT 後用 `trend_veto` audit 再評估。
- Nautilus 借鏡：event catalog + cache 抽象；不借 Rust 熱路徑 / MQ。

**Pending**
- HTF / NDJSON：待 UAT tick。

**Live 連線護欄（P4-13，已落地）**
- 暖機期禁止新 entry；單日斷線 ≥3 → `block_new_entry`；有倉斷線 → CRITICAL。

---

### 2026-06-16（文件重構 — archive）

**目前進度**
- BackTestingSpec 拆至各 package；WeeklyStatus 舊節 → `ARCHIVE/`。

*詳見 [`ARCHIVE/weekly-status-2026.md`](ARCHIVE/weekly-status-2026.md)。*