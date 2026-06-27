---
id: FT-003-ENTRY-FUNNEL
parent: FT-003
status: Active
opened: 2026-06-27
---

# FT-003 Phase 3.6 — 進場漏斗統計（Methods SSOT）

> **定位**：Phase 3.6 **§C 進場平面** 的指標操作定義、cohort 分層、固定窗口與解讀邊界。  
> **契約摘要**：[`SPEC.md`](SPEC.md) §4.6 · **執行步驟**：[`PLAN.md`](PLAN.md) Phase 3.6 · **產物模板**：[`workspaces/_template/volatility_baseline.md`](../../../workspaces/_template/volatility_baseline.md) §C  
> **腳本狀態**：`ft003_episode_diagnosis.py` **待實作**；本檔為文件 SSOT，不依賴腳本已存在。

---

## 1. 研究定位

### 1.1 與 Phase 3.6 其他平面的關係

| 平面 | 產物章節 | 回答的問題 |
|------|----------|------------|
| 市場尺度 | `VOLATILITY_BASELINE.md` §A/B | 固定點數停損 vs 當月 ATR / 1m range 是否脫節 |
| **進場漏斗** | **§C（本檔）** | 動能武裝後脈衝是否延續、回踩是否可達、vol 門檻是否合理 |
| 出場診斷 | §D | exit reason、QSL、expectancy_by_reason（毛點） |

**四平面診斷** = 尺度 §A/B + **進場 §C** + 出場 §D；合成敘事見 [`strategy_diagnosis.md`](../../../workspaces/_template/strategy_diagnosis.md) §6。

### 1.2 診斷 only（MUST — 複述 SPEC §4.6）

- 產出 **禁止** 用於本輪 `leaderboard` 排名或修改已提交 `params`。
- 2026-05 統計 **僅** 供 holdout **風險敘事**；**禁止** 依 5 月分布回頭改本輪 grid。
- 診斷 **MUST NOT** 輸出「建議參數值」供直接寫入 config（描述統計、ratio、分位除外）。
- 第二輪 sweep 仍須 SPEC §4.4 人類書面批准。

### 1.3 三種研究問題（不可混談）

| 問題 | 本檔章節 | 說明 |
|------|----------|------|
| **脈衝延續性** | §4 | armed 後固定 Δt 內價格是否沿武裝方向位移 |
| **回踩可達性** | §5 | VWAP band + vol 衰竭雙條件能否在 timeout 內同時滿足 |
| **進場後 edge** | §D（出場診斷） | 實際成交後的 PnL；**不在本章 tune 進場 knob** |

**解讀邊界（Discussion MUST）**：

- armed 後「順勢」≠ 策略 **net edge**（設計為 **不追價**、等回踩）。
- §C 毛點 / forward 位移與 §D 一併閱讀時，net KPI 須扣 [`SHARED_ASSUMPTIONS.md`](../../../workspaces/SHARED_ASSUMPTIONS.md) §3.1 摩擦 **5 點/趟**。
- 順勢統計用於 **假說生成**；valid 區間 grid 調整仍須 overfitting 協議（[`SPEC.md`](SPEC.md) §4）。

---

## 2. 策略漏斗（對齊程式）

兩段式進場（[`strategy.py`](../../../packages/strategies/vwap-momentum/src/strategy_vwap_momentum/strategy.py)）：

```text
flat
  → momentum_armed     （vol_1s ≥ threshold 且 buy/sell_ratio 通過）
  → [pullback ticks]   （每 tick：near_vwap ∧ vol_dried_up ? entry : near_miss 計數）
  → entry | momentum_timeout | trend_veto | structure_veto | risk_blocked
```

`NearMissTracker` truth table（[`observability.py`](../../../apps/trading-app/src/observability.py)）— `(near_vwap, vol_dried_up)`：

| near_vwap | vol_dried_up | 結果 |
|-----------|--------------|------|
| T | T | 進場（非 near_miss） |
| T | F | `blocked_vol_only` |
| F | T | `blocked_vwap_only` |
| F | F | `blocked_both` |

其中 `vol_dried_up` ≡ `vol_1s ≤ exhaustion_vol`；`near_vwap` ≡ `|price − VWAP| ≤ entry_band_points`。

---

## 3. 操作定義 — `vol_1s`

### 3.1 符號表

| 符號 | 定義 | 單位 | 備註 |
|------|------|------|------|
| `vol_1s` | 滾動 1 秒成交 **口數** | contracts | **≠** 價格點數；**≠** 1m High−Low |
| `buy_vol_1s` | 1 秒內買方成交量 | contracts | |
| `sell_vol_1s` | 1 秒內賣方成交量 | contracts | |
| `buy_ratio` | `buy_vol_1s / vol_1s`（`vol_1s > 0`） | 0–1 | Long 武裝門檻 |
| `sell_ratio` | `sell_vol_1s / vol_1s` | 0–1 | Short 武裝門檻 |
| `momentum_vol_1s` | config 基礎爆量門檻 | contracts | 預設 150 |
| `session_multiplier` | 開盤時段倍率 | 無因次 | 來自 engine vol_threshold |
| `threshold` | `momentum_vol_1s × session_multiplier` | contracts | 實際武裝門檻 |
| `exhaustion_vol` | 進場時 `vol_1s ≤` 此值視為量能枯竭 | contracts | 預設 15 |

### 3.2 兩道門的語意

| 階段 | 條件 | 交易解讀 |
|------|------|----------|
| **武裝** | `vol_1s ≥ threshold` 且 ratio 通過 | 偵測 **右尾 spike**（罕見秒）；非「比一般稍活躍」 |
| **進場** | `vol_1s ≤ exhaustion_vol` 且 near_vwap | spike 後 **量能枯竭整理**，才貼 VWAP 進場 |

背景 `vol_1s` 分布（TMFR1 tick，2026-01～05）通常 p50 個位數、p99 約 60–80；`threshold=150` 意味武裝事件落在全日 vol 分布 **極右尾**（須以腳本算 `P(vol_1s ≥ threshold)` 確認）。

### 3.3 MUST 統計（P1）

| 指標 | 公式 / 定義 | 分層 |
|------|-------------|------|
| `pct_vol_gte_threshold` | `#{vol_1s ≥ threshold} / #{samples}` × 100 | 月、時段 |
| `pct_vol_lte_exhaustion` | `#{vol_1s ≤ exhaustion_vol} / #{samples}` × 100 | 月、時段 |
| `vol_1s_at_arm` 分布 | armed 當下 `vol_1s` 的 p50/p90 | outcome cohort |
| `buy_ratio_at_arm` 分布 | armed 當下 ratio | Long / Short |
| `vol_when_blocked_vol_only` | `blocked_vol_only` tick 的 `vol_1s` 分布 | episode |

資料來源：`tick_cache/` tick CSV；armed 時刻取自 `DECISION_AUDIT event_type=momentum_armed`。

---

## 4. P0 — armed 後固定窗口「是否順勢」

### 4.1 Cohort 單位

每筆 **`DECISION_AUDIT`** 且 `event_type=momentum_armed`，必含：

- `episode_id`
- `direction`（`Long` / `Short`）
- `trigger_price`（或等價 `price` 欄位）
- `ts`（exchange epoch seconds）

### 4.2 固定 Δt（MUST 預註冊）

**禁止** 依結果事後挑選窗口。

| 窗口 ID | Δt（秒） | 用途 |
|---------|----------|------|
| W30 | 30 | 脈衝當下延續 |
| W60 | 60 | 短延續 |
| W180 | 180 | 對齊預設 `momentum_timeout_sec` |
| W300 | 300 | timeout 敏感性（診斷級；**非** tune 依據） |

### 4.3 方向符號

- Long：`sign = +1`；有利偏移 = 價格上漲
- Short：`sign = −1`；有利偏移 = 價格下跌

### 4.4 每 cohort × 每 Δt 輸出

自 `trigger_price` 起，在 `[ts, ts+Δt]` 內 tick close 序列計算：

| 指標 | 公式（Long 例） | 單位 |
|------|-----------------|------|
| `MFE_delta` | `sign × max(price − trigger_price)` | 點 |
| `MAE_delta` | `sign × min(price − trigger_price)` 取不利側絕對值 | 點 |
| `close_delta` | `sign × (close_{ts+Δt} − trigger_price)` | 點 |
| `signed_return_over_atr` | `close_delta / ATR20_p50`（當日或當月，須註明） | 無因次 |
| `hit_entry_band` | 是否曾 `|price − VWAP| ≤ entry_band_points` | bool |

彙總：各 outcome cohort 的 `MFE_delta` / `MAE_delta` / `close_delta` 之 **mean、median、p50、p90**。

### 4.5 Outcome 分層（MUST）

每 episode 終局標籤（互斥優先序建議）：

1. `entered` — 產生 entry `SIGNAL_AUDIT`
2. `trend_veto` / `structure_veto` — 有 veto `DECISION_AUDIT` 且無 entry
3. `risk_blocked` — `risk_blocked` 事件
4. `timeout` — `momentum_timeout` 且無 entry

報表 **MUST** 分 cohort 輸出；禁止只報全樣本平均。

### 4.6 與 forward PnL harness 的關係

[`forward_pnl.py`](../../../apps/trading-app/src/reporting/forward_pnl.py) 的 `ForwardPnlPolicy`（`fixed_seconds` 等）與 [`trend_calibration.py`](../../../apps/trading-app/src/reporting/trend_calibration.py) 語意一致；但本檔 cohort 為 **armed**，非 trend veto 候選。若使用同一 policy，**MUST** 在 JSON 產物註明 `cohort=momentum_armed` 與 `policy_summary`。

---

## 5. P0 — 回踩（pullback）漏斗

### 5.1 Episode 級指標

優先於日彙總 `near_miss` 計數；每 `episode_id` 一列：

| 指標 | 定義 | 單位 |
|------|------|------|
| `time_to_first_band` | `armed_ts` → 首次 `near_vwap` 為真 | 秒 |
| `time_to_entry` | `armed_ts` → entry signal `ts` | 秒 |
| `pullback_depth` | armed 後逆勢最大回撤：Long 為 `trigger − min(price)`；Short 為 `max(price) − trigger` | 點 |
| `pullback_depth_over_atr` | `pullback_depth / ATR20` | 無因次 |
| `vol_at_arm` | armed 當下 `vol_1s` | contracts |
| `vol_at_entry` | entry 當下 `vol_1s`（若 entered） | contracts |
| `vwap_distance_at_entry` | entry 時 `|price − VWAP|` | 點 |
| `closest_vwap_distance` | episode 內 `|price − VWAP|` 最小值 | 點 |

`closest_vwap_distance` 報 **分布**（p50/p90/min），非僅全域 min。

### 5.2 漏斗轉化率（MUST）

```text
armed
  → ever_near_vwap      (% of armed)
  → ever_vol_dried      (% of armed)
  → both_same_tick      (% of armed; 理論可進場瞬間)
  → entered             (% of armed)
  → timeout             (% of armed)
```

各階段條件：

- `ever_near_vwap`：episode 內至少一 tick `near_vwap`
- `ever_vol_dried`：至少一 tick `vol_1s ≤ exhaustion_vol`
- `both_same_tick`：至少一 tick 同時 near_vwap ∧ vol_dried
- `entered`：有 entry signal
- `timeout`：`momentum_timeout` 且無 entry

### 5.3 Near-miss 月彙總方法論

日終 `DAILY_SUMMARY.near_miss` 來自 [`NearMissTracker`](../../../apps/trading-app/src/observability.py)（當日 reset）。

**多 valid 日報告 MUST**：

| 欄位 | 月彙總方式 |
|------|------------|
| `blocked_both`, `blocked_vwap_only`, `blocked_vol_only` | **sum** over `daily_summaries` |
| `momentum_episodes`, `momentum_timeout` | **sum** |
| `closest_vwap_distance` | **min** over days |

**已知限制（script fix pending）**：[`uat_report.py`](../../../apps/trading-app/src/reporting/uat_report.py) 組 multi-day JSON 時頂層 `near_miss` 目前僅取 **最後一日**；Phase 3.6 腳本 **MUST** 自行聚合 `daily_summaries`，不可直接信任頂層欄位。

### 5.4 假說 ↔ knob 對照（診斷用，非自動建議參數）

| 觀察 | 可能解讀 | 研究 knob（第二輪須人類批准） |
|------|----------|-------------------------------|
| `blocked_vwap_only` 高 | 價格 rarely 回 VWAP | `entry_band_points` |
| `blocked_vol_only` 高 | 進 band 但 vol 未枯竭 | `exhaustion_vol` |
| `blocked_both` 高 | 雙條件難同時滿足 | `momentum_timeout_sec` |
| timeout 高且 `closest_vwap_distance` 小 | 差一口進場 | band 微調 |
| timeout 高且 closest 大 | 脈衝後單邊走、不回 VWAP | 結構性不匹配；非單一 knob |

---

## 6. P1 — `momentum_timeout` 窗口

| 指標 | 定義 |
|------|------|
| `timeout_rate` | `momentum_timeout / momentum_episodes` |
| `time_to_timeout` | 對 timeout episode：`timeout_ts − armed_ts`（應 ≈ `momentum_timeout_sec`） |
| `timeout_before_ever_band` | timeout 且從未 `ever_near_vwap` 占比 |
| `timeout_after_band_no_vol` | timeout 且曾 near_vwap 但從未 vol_dried 占比 |

**敏感性（診斷級，P1）**：counterfactual 窗口 {120, 180, 240}s 下 **漏斗轉化率變化** 僅記錄於報告；**禁止** 依此直接寫入 config。

---

## 7. P2 — 時段與延伸

### 7.1 時段分層

與 PLAN Phase 3.6 P2 對齊（可選 `--session-buckets`）：

| Bucket | 時段（交易所時間） |
|--------|-------------------|
| `open_30m` | 開盤後 30 分鐘 |
| `mid` | 中盤 |
| `close_1h` | 尾盤 1 小時 |

§4–§6 指標 **SHOULD** 可按 bucket 複表。

### 7.2 延伸指標

| 指標 | 說明 | 銜接 |
|------|------|------|
| 進場後 MFE/MAE by `exit_reason` | 持倉至出場 | §D 出場診斷 |
| `episode_funnel` | armed / entered / timeout / veto | `DAILY_SUMMARY` |
| `pressure.*` | 連續 timeout、armed_to_entered_ratio | FT-001 REVIEW §3.1 |

---

## 8. 資料來源與 CLI 契約

### 8.1 輸入

| 來源 | 用途 |
|------|------|
| `workspaces/<agent>/logs/baseline_valid.log` | `DECISION_AUDIT`, `SIGNAL_AUDIT`, episode timeline |
| `workspaces/<agent>/reports/baseline_valid.json` | `daily_summaries`（near_miss 月 sum） |
| `tick_cache/{code}_{date}.csv` | MFE/MAE/close_delta、vol 分布 |
| `workspaces/<agent>/config/config.yaml` | `entry_band_points`, `momentum_timeout_sec`, vol 門檻 |

### 8.2 產出（script pending）

| 產物 | 說明 |
|------|------|
| `workspaces/reports/entry_funnel.json` | 機器可讀；含 schema_version、policy、cohort 表 |
| `VOLATILITY_BASELINE.md` §C | 人類可讀；由 `ft003_episode_diagnosis.py` 填入 |

**Future CLI**（契約預定）：

```bash
cd apps/trading-app/src
export PYTHONPATH=.
python scripts/ft003_episode_diagnosis.py \
  --agent agent-conservative \
  --cache-dir ../../../tick_cache \
  --from-date 2026-04-01 --to-date 2026-04-30 \
  --markdown-append ../../../workspaces/VOLATILITY_BASELINE.md \
  --json-out ../../../workspaces/reports/entry_funnel.json
```

### 8.3 JSON 頂層欄位（契約草案）

```json
{
  "schema_version": 1,
  "agent": "agent-conservative",
  "from_date": "2026-04-01",
  "to_date": "2026-04-30",
  "config": { "entry_band_points": 2.0, "momentum_vol_1s": 150, "exhaustion_vol": 15, "momentum_timeout_sec": 180 },
  "forward_policy": { "windows_sec": [30, 60, 180, 300], "atr_source": "kbar_month_p50" },
  "vol_threshold_coverage": { },
  "armed_forward_by_outcome": { },
  "pullback_funnel": { },
  "timeout_diagnostics": { },
  "near_miss_month_aggregate": { }
}
```

---

## 9. 禁止事項

- 不得用 §C 診斷結果修改本輪 `leaderboard` 或已提交 `params`。
- 不得用 2026-05 統計回頭 tune valid grid。
- 不得輸出「建議 config 數值」；僅描述統計、ratio、分位。
- 不得將 armed forward 順勢直接等同 Pilot 獲利預測（[`SHARED_ASSUMPTIONS.md`](../../../workspaces/SHARED_ASSUMPTIONS.md) §2）。
- W300 與 timeout counterfactual **禁止** 作為本輪 sweep 選參依據。

---

## 10. 交叉引用

| 文件 | 內容 |
|------|------|
| [`SHARED_ASSUMPTIONS.md`](../../../workspaces/SHARED_ASSUMPTIONS.md) §4.2 | vol_1s 兩道門、與 §4.1 尺度並列 |
| [`packages/strategies/vwap-momentum/SPEC.md`](../../../packages/strategies/vwap-momentum/SPEC.md) §5 | 策略決策流程 |
| [`PLAN.md`](PLAN.md) Phase 3.6 | Gate、驗收 checklist |
| [`AGENT_ROSTER.md`](AGENT_ROSTER.md) §1.7 | Phase 3.6 執行者 prompt |
