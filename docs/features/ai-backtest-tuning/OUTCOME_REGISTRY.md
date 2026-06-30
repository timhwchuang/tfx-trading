---
id: OUTCOME-REGISTRY
parent: ALPHA-PLAYBOOK
version: 1.0
status: Active
opened: 2026-06-30
---

# Outcome Registry — Alpha Phase 0 結案分類（v1.7）

> **目的**：`MVPClosed` umbrella 下拆 **死因**，避免錯殺與設計錯誤混為一談。  
> **gate_report §Decision MUST**：`outcome_class` + 既有 `outcome` 細碼。  
> **SSOT 流程**：[`ALPHA_RESEARCH_PLAYBOOK.md`](ALPHA_RESEARCH_PLAYBOOK.md) v1.7 · [`HOLDOUT_CONTRACT_v2.md`](HOLDOUT_CONTRACT_v2.md) v2.3

---

## 1. 分層表

| 層級 | `outcome_class` | 意義 | 典型 FT | closure_review |
|------|-----------------|------|---------|:--------------:|
| **L0** | `design_error` | 上游無樣本 / 錨點錯 | FT-017 | 否 — 新 proposal |
| **L1** | `no_gross_edge` | 契約 gross 天花板 < 摩擦緩衝 | FT-019 G1 | 否 |
| **L1** | `direction_falsified` | fingerprint / W 窗 ≤0 | FT-013 | 否 |
| **L2** | `execution_gap` | 方向 OK、契約 net≤0 或 med≤0 | FT-016 | 新 exit FT **一次** |
| **L2** | `skew_profile_fail` | G1/G2 過、skew 次級不過 | FT-018 | **可**（§2.3 Class Appeal） |
| **L2** | `fingerprint_contract_mismatch` | J1 過、J2 契約 gross<3 | （v1.7 新案） | exit-led 新 FT |
| **L2** | `sample_sparse` | 方向正、n<G3/G3S | FT-014 | 新 thesis 觸發 |
| **L3** | `valid_regime_fail` | train 正、valid net≤0 | FT-018 valid | holdout 禁；登 near-miss |
| **L4** | `near_miss_train_positive` | train net_total>0、phase0 過、次級未過 | FT-018 | 可申訴 |

---

## 2. 細碼對照（既有 `outcome` → `outcome_class`）

| outcome 細碼 | outcome_class |
|--------------|---------------|
| `spec_anchor_mismatch` / `compress_gate_unreachable` | `design_error` |
| `*_fingerprint_fail_direction` | `direction_falsified` |
| `*_fingerprint_fail_n` | `sample_sparse` |
| `*_fingerprint_pass_g1_fail` | `no_gross_edge` |
| `*_no_skew_champion` / `gudt_no_skew_champion` | `skew_profile_fail` |
| `fingerprint_contract_mismatch` | `fingerprint_contract_mismatch` |
| `closure_review_passed_mean_track` | （申訴通過標記） |

---

## 3. 工具映射

`reporting.gate_summary.build_gate_summary()` 產 `outcome_class` + `warnings`：

| warning | 意義 |
|---------|------|
| `NON_CONTRACT_horizon_*` | horizon 正 total — **不得當 gate** |
| `FINGERPRINT_TRAP_SUSPECT` | fingerprint 過、契約 gross/趟 < 3 |
| `TRAIN_NET_POSITIVE_BUT_PHASE0_FAIL` | 帳面正但 G1/G2 未過 |

---

## 4. Near-miss

train `net_total > 0` 且 `outcome_class` ∈ {`skew_profile_fail`, `sample_sparse`, `near_miss_train_positive`} → 登錄 [`NEAR_MISS_REGISTRY.md`](../../../workspaces/NEAR_MISS_REGISTRY.md)。

**禁止**依 registry 自動 tune。

---

## 參考

- [`META_REVIEW_BRIEF.md`](META_REVIEW_BRIEF.md)
- [`CORPSE_ATLAS.md`](../../../workspaces/CORPSE_ATLAS.md)
