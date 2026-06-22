# Phase 0 完成簽核 — 2026-06-22

| 步驟 | 項目 | 完成 |
|------|------|------|
| 0.1 | monorepo 根 + 分支 main | ☑ |
| 0.2 | setup-dev.sh | ☑ |
| 0.3 | run-all-tests（app 1 fail，見 setup_20260622.txt） | ☑* |
| 0.4 | reports/ snapshots/ uat_evidence/ | ☑ |
| 0.5 | 模擬環境變數（uat-env.sh，未 commit） | ☑ |
| 0.6 | simulation: true + log 目錄 | ☑ |
| 0.7 | live 冒煙（登入 + ATR + DECISION_AUDIT） | ☑ |
| 0.7b | reports/day20260622.json | ☑ |
| 0.8 | snapshots/config_20260622.yaml | ☑ |

\* 1 項 determinism 測試失敗與 kbars 落盤共存；Phase 1 前可再跑一輪全綠確認。

**簽名**：________________ **日期**：2026-06-22

**證據路徑**：
- `uat_evidence/phase0/setup_20260622.txt`
- `uat_evidence/phase0/live_smoke_20260622.txt`
- `snapshots/config_20260622.yaml`
- `reports/day20260622.json`
