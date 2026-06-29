# Entry Lab — 憲章

> **定位**：與 [Alpha Playbook](../docs/features/ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md) **平行**的進場／執行診斷軌道。  
> **不是** gate、不是 THESIS_QUEUE 狀態機、不是 CAL-8 復活。

## 目的

在 **封印 P0 進場** 上回答：

1. 進場方向對幾次？（path）
2. 趨勢延續多久？（horizon decay）
3. 為何操作失敗？（exit_gap · 契約 PnL）
4. 時空／regime 背景？（順逆勢 · 進場解剖）

## 戒律

1. **固定 entry P0** — 不 tune grid、不改 exit sim 參數（Track F 除外、僅附錄）
2. **描述 + 分群** — 不輸出「建議參數值」供直接寫 config
3. **不得** 回寫 `gate_report` 或推翻 MVPClosed verdict

## 與 Playbook 邊界

| Entry Lab 允許 | Playbook 禁止 |
|----------------|---------------|
| 探索 regime／filter cohort | 事後 filter rescue 已結案 grid |
| 產生 THESIS_BRIEF 假說草稿 | 同一 FT 第三輪 exit 魔改 |
| bootstrap CI · 假說生成 | 依 post_entry 回頭 tune train |

CAL-8 誤解：見 Playbook **附錄 A** — filter 探索在 Lab **合法**；promote 須 pre-register 新 FT。

## 第一輪 Corpus

GDC · GUDT · FRP · SFBT（liquidity/continuation 四案）

## 產物

- `corpus/` — per-trade JSON + manifest
- `reports/` — baseline、regime、paired、FILTER_CANDIDATES
- 方法封印：[`ENTRY_LAB_PROTOCOL.md`](ENTRY_LAB_PROTOCOL.md)
