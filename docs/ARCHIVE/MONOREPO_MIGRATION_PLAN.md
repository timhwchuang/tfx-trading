# tfx-trading Monorepo — Migration Plan (archived)

> **Archived 2026-06-17** — 遷移已完成。現行規格見根目錄 [`SPEC.md`](../../SPEC.md)。  
> Retained for historical reference only — do not edit.

---

## Decisions (locked)

| Item | Choice |
|------|--------|
| GitHub repo | `timhwchuang/tfx-trading` |
| Git history | Fresh start (single initial migration commit) |
| Old repos | Archive only; README redirect |
| Strategy layout | **`packages/strategies/vwap-momentum/`** (not flat `packages/strategy-vwap-momentum/`) |

---

## Target tree (delta from four-repo layout)

```text
packages/trading-engine/          ← was trading-engine/
packages/trading-backtest/        ← was trading-backtest/
packages/strategies/vwap-momentum/  ← was strategy-vwap-momentum/
apps/trading-app/                 ← was trading-app/
```

---

## Phase 0 — Docs

- [x] `monorepo/SPEC.md`（已併入根 `SPEC.md`）
- [x] `monorepo/Plan.md`（本檔）
- [x] GitHub repo `tfx-trading` created

---

## Phase 1 — Restructure directories

- [x] Create `packages/`, `packages/strategies/`, `apps/`
- [x] Move trees; remove nested `.git/`
- [x] Consolidate CI at root; merge `.gitignore`

---

## Phase 2 — Dependencies & scripts

- [x] `scripts/setup-dev.sh` (auto `.venv`)
- [x] Path editable `requirements.txt`
- [x] `ci-setup.sh`, `run_tests.py` paths

---

## Phase 3 — CI & test runner

- [x] `scripts/run-all-tests.sh` (four suites, no `theman`)
- [x] Root `.github/workflows/ci.yml`

---

## Phase 4 — Documentation & Windows ops

- [x] Root `README.md`, `SPEC.md`, `CHANGELOG.md`, `docs/Architecture.md`, `docs/DOC_MAP.md`
- [x] Docs slim: centralized `docs/` (uat, ops); package roots SPEC+README only
- [x] App Architecture stub → root; UPGRADE_RUNBOOK deprecated
- [x] `WeeklyStatus.md` migration section
- [x] Windows `.ps1` paths → `-MonorepoRoot C:\tfx-trading`

---

## Phase 5 — Publish

- [x] `git init`, initial commit `39b6c2d`
- [x] `git push origin main` → `timhwchuang/tfx-trading`
- [x] Optional tag: `v0.3.0-monorepo`（遷移里程碑；非每日必需）

---

## Phase 6 — Archive old repos (after gates)

**Gates (all must pass before Archive)**

- [ ] Clean venv: `bash scripts/setup-dev.sh` OK
- [ ] `bash scripts/run-all-tests.sh` all green
- [ ] GitHub Actions green on `main`
- [ ] Windows: `apps/trading-app` live/backtest smoke documented

**Per old repo**

- [ ] Final README banner → push → GitHub Archive

| Repo | New path in monorepo |
|------|----------------------|
| trading-engine | `packages/trading-engine` |
| trading-backtest | `packages/trading-backtest` |
| strategy-vwap-momentum | `packages/strategies/vwap-momentum` |
| trading-app | `apps/trading-app` |