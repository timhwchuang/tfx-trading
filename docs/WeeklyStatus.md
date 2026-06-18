# Weekly Status — 人機協作開發日記

> 給**人類**看的進度、Follow-up、待決策。工程路線圖見 [`TODO.md`](TODO.md)；文件職責見 [`DOC_MAP.md`](DOC_MAP.md)。  
> **歷史週報**（2026-06-12～06-16）→ [`ARCHIVE/weekly-status/weekly-status-2026.md`](ARCHIVE/weekly-status/weekly-status-2026.md)

**用法**：重大決策時在下方新增一節（最新放最上面）。

---

## UAT 週報必填欄位（Phase 3 起）

每週更新（可併入下方範本）：

| 欄位 | 來源 / 備註 |
|------|-------------|
| Expectancy (gross) / (net) | monorepo 根：`python -m reporting reports\day*.json --trend`（JSON 報告檔） |
| Sharpe、MDD 使用率 | 同上 |
| 券商日損益 vs `daily_summaries[-1].pnl.daily_pnl_points` | `python -m reporting.uat_evidence_export broker reports\day*.json`；差異 >0.5 點須註記 |
| Tick 分層 | `python -m reporting.uat_evidence_export tick reports\day*.json` → `phase4_stress/tick_quality_stratification.csv` |
| near-miss 本週摘要 | timeout / veto / 未成交；無則寫「本週無」 |
| `type0_pct` 偏高日 | conversion / expectancy 是否異常（Phase 4 起） |

Phase 5 審核前另附：**前 5 大虧損日**表（日期、round-trip、當日 net、備註）。

## 範本（複製用）

```markdown
### YYYY-MM-DD（週次 / 標題一句話）

**UAT 指標（本週）**
- Expectancy gross: ___ / net: ___
- Sharpe: ___ | MDD 使用率: ___%
- 摩擦對帳：券商 vs log 最大單日差異 ___ 點（原因：___）
- near-miss：___

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

### 2026-06-18（模擬 API 金鑰就緒 — UAT Phase 0 開跑）

**目前進度**
- 永豐**模擬** API 金鑰已備妥；工程 blocker 解除。
- `bash scripts/run-all-tests.sh` 全綠（以 `Ran N tests` 為準；含 reporting JSON trend 測試）。
- 證據骨架：[`uat_evidence/`](../uat_evidence/)（範本 + phase 子目錄）、`reports/`、`snapshots/`。
- UAT 清單已補強：gross/net、摩擦對帳、tick 分層、壓力情境審閱（見 [`uat/APP.md`](uat/APP.md)）。

**人類必做（Follow-up）**
- [ ] Windows UAT 機：`setup-dev.sh` + 設定 `SJ_API_KEY` / `SJ_SEC_KEY` / `TICK_ARCHIVE=1` / `KBARS_ARCHIVE=1` / `LOG_FILE`
- [ ] 完成 [`uat/APP.md`](uat/APP.md) Phase 0（含首次 `python -m live` 10 分鐘）
- [ ] Phase 1 首個完整交易日 → `reports/day*.json` + determinism hash
- [ ] Phase 3 起建議 `friction.enabled: true`；每週填 `uat_evidence/templates/weekly_kpi_snapshot.md`

**Pending / 待決策**
- 舊四 repo GitHub Archive（仍待人類操作）
- P4-13-F 斷網實機、Phase 6 Telegram 實機 — 待 Phase 4/6 演練

**備註**
- **尚未落地、不阻擋 UAT**：P2-1 多口、P6-4 sizing、P6-5 追價、NDJSON sink、FT-001 audit replay（規劃中）。
- **UAT 即可用**：tick/kbar archive、reporting KPI、determinism_check、near-miss、P4-13 護欄、calibration_cli（trend 預設關）。

---

### 2026-06-17（Monorepo 遷移完成 + 文件/Windows 路徑對齊）

**目前進度**
- **`timhwchuang/tfx-trading`** monorepo 已上線；tag `v0.3.0-monorepo`；CI 綠燈。
- 路徑：`packages/trading-engine`、`packages/trading-backtest`、`packages/strategies/vwap-momentum`、`apps/trading-app`。
- 整合文件：[`SPEC.md`](../SPEC.md)（§7 架構）、[`DOC_MAP.md`](DOC_MAP.md)。
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
| **Monorepo** | [`tfx-trading`](https://github.com/timhwchuang/tfx-trading) — `bash scripts/setup-dev.sh`；見 [`SPEC.md`](../SPEC.md) |
| **永豐模擬 API** | **金鑰已就緒**（2026-06-18）；UAT 不需 CA。 |
| **UAT 累積 tick** | `TICK_ARCHIVE=1` 每日落盤 → repo 根 `tick_cache/`。 |
| **KBARS_ARCHIVE** | 建議 UAT 一併開啟，供 ATR / 趨勢回測熱身。 |
| **UAT 執行** | Phase 0 開跑 → [`uat/APP.md`](uat/APP.md)；證據 [`uat_evidence/`](../uat_evidence/) |
| **Phase 6 CAL B 類** | 待 UAT tick；見 [`TODO.md`](TODO.md) §P6-1-CAL + vwap [`SPEC.md` §6.1](../packages/strategies/vwap-momentum/SPEC.md) |
| **Pilot 門檻 SSOT** | [`uat/APP.md`](uat/APP.md) Phase 5（其他檔僅摘要） |
| **週報 KPI** | Phase 3 起：gross/net + 券商對帳 + near-miss（見本檔「UAT 週報必填欄位」） |
| **文件分層** | 架構 → 根 [`SPEC.md`](../SPEC.md) §7；週報 → 本檔；可開工 → [`TODO.md`](TODO.md) |

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