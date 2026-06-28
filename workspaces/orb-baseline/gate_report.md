# FT-009 Gate Report — orb-baseline（Phase 0）

> **Thesis F**：Opening Range Breakout — 開盤區間 first break only。  
> **主判**：**01–04 合計**（pre-registered 參數，無事後切片）。

| 區間 | 產物 | Phase 0 |
|------|------|---------|
| **01–04** 2026-01-01～2026-04-30 | [`counterfactual_orb_0104.json`](reports/counterfactual_orb_0104.json) | **通過** |
| Valid 2026-04-01～2026-04-30 | [`counterfactual_orb_valid.json`](reports/counterfactual_orb_valid.json) | 未過（參考） |

## 01–04 主判 — summary_by_param

| param | n | gross/趟 | net/趟 | break_days |
|---|---|----------|--------|------------|
| rm15_bk0 | 74 | **5.99** | **0.99** | 74 |
| rm15_bk0p15 | 74 | **5.99** | **0.99** | 74 |
| rm30_bk0 | 73 | 5.61 | 0.61 | 73 |
| rm30_bk0p15 | 73 | **7.93** | **2.93** | 73 |

### Best passing（01–04）

- **rm30_bk0p15**：n=73 gross=**7.93** net=**2.93**

### 方向拆解（rm30_bk0p15 — 最佳毛期望）

| 方向 | n | gross/趟 | net/趟 |
|------|---|----------|--------|
| **Short** | 28 | **+19.60** | **+14.60** |
| Long | 45 | +0.67 | **−4.33** |

**解讀**：01–04 通過主要由 **30 分鐘區間向下突破**貢獻；Long 全期為負。gross_median 仍為 **−6**（多數單筆停損），均值靠少數大贏單拉高 — 與 FT-006 不同，需 **holdout + 方向穩健性** 再開 plugin。

### 較均衡候選（rm15_bk0）

| 方向 | n | gross/趟 | net/趟 |
|------|---|----------|--------|
| Long | 43 | +5.22 | +0.22 |
| Short | 31 | +7.05 | +2.05 |

---

## Valid 2026-04（參考 only — 非主判）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| rm15_bk0 | 20 | **+8.64** | **+3.64** |
| rm30_bk0p15 | 19 | +1.54 | **−3.46** |

4 月 **rm15** 優於 **rm30** — 再次顯示 param 穩健性疑慮；**不可**僅因 rm30 01–04 毛期望最高就當唯一真相。

---

## 對照（全 thesis）

| Thesis | 01–04 最佳 | 備註 |
|--------|-----------|------|
| FT-006 fade | valid 過 / holdout 掛 | 均值回歸 |
| FT-008 breakout | gross +4.40 net −0.60 | close_1h |
| **FT-009 ORB** | gross **+7.93** net **+2.93** | **首個 01–04 Phase 0 過關** |

---


## Plugin baseline（Phase 1 — 01–04）

| 指標 | Phase 0 CF | Plugin（P1+P3 後） |
|------|------------|-------------------|
| trades | 73 | **73** |
| gross/趟 | **+7.93** | **+6.29** |
| net/趟 | **+2.93** | **+1.29** |
| intent_cancel | — | **0** |
| QSL | — | 1.4% |

**對帳修復**：P1 `ioc_slippage=50` + `pending_timeout=30`；P3 純 `k×ATR` 屏障；P0 session SMA(TR) ATR。差距 −119 gross（TP 漏接 6 天仍存）。

---

## Holdout 2026-05（v1 封印）

| 來源 | param | n | gross/趟 | net/趟 |
|------|-------|---|----------|--------|
| CF | rm30_bk0p15（凍結） | 19 | **−3.64** | **−8.64** |
| CF | rm15_bk0（穩健候選） | 19 | +8.89 | +3.89 |
| Plugin | rm30_bk0p15 | 19 | **−3.79** | **−8.79** |

產物：[`counterfactual_orb_holdout.json`](reports/counterfactual_orb_holdout.json)、[`baseline_holdout.json`](reports/baseline_holdout.json)

**v1 標記**（[`HOLDOUT_CONTRACT_v2.md`](../../docs/features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) §5.4）：**`holdout_fail_structural`** — train 曾有 3.1 紅旗（median −6、Short 厚尾），單月 net 負 → **可結案**，不等待 06。

---

## Holdout v2（05+06 合併 — 待 06 資料）

| 項目 | 狀態 |
|------|------|
| 契約 | [`HOLDOUT_CONTRACT_v2.md`](../../docs/features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) |
| 區間 | 2026-05-01～2026-06-30 |
| tick_cache 06 | **未落地** — 合併 holdout **未跑** |
| CLI | `run_cf_holdout.py --holdout-v2` · `ft009_run_baseline.py --holdout-v2` |
| 預期 | 06 落地後僅作**存檔複驗**；v1 結論已保留，**不**事後換 rm15 |

### v2 冠軍資格（01–04 事後檢視 — rm30_bk0p15）

| 檢查 | 結果 |
|------|------|
| G1–G3（01–04） | ☑ |
| gross_median > −5 | **✗**（−6） |
| 單邊 gross > 80% | **✗**（Short 主導） |
| Long train net > −3 | **✗**（−4.33） |
| **3.1 disqualify** | **是** — 依 v2 本不應進 holdout；v1 已跑完作教訓存檔 |

---

## §Decision

| 欄位 | 值 |
|------|-----|
| Phase 0 | **通過**（01–04 rm30_bk0p15） |
| Phase 1 plugin | **完成** — 73/73 成交、net +1.29 |
| Holdout 05 v1 | **未過** — `holdout_fail_structural` |
| Holdout v2 05+06 | **未跑**（06 待 backfill） |
| 決策 | **No-Go UAT** — 維持 `strategy-vwap-momentum`；FT-009 **MVPClosed** |
| 備註 | rm15 穩健性僅供下一 thesis 參考，不作本輪事後主判 |
| 日期 | 2026-06-28 |
