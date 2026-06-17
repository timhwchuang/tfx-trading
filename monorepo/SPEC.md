# tfx-trading Monorepo — Authoritative Spec

> **Status**: migrated  
> **Repo**: [`timhwchuang/tfx-trading`](https://github.com/timhwchuang/tfx-trading)  
> **整合入口**: [`../SPEC.md`](../SPEC.md) · **架構**: [`../docs/Architecture.md`](../docs/Architecture.md)  
> **Execution checklist**: [`Plan.md`](Plan.md)

---

## 1. Purpose

Single git repository for TXF futures trading research and UAT:

- **Kernel** (`trading-engine`) — state machine, risk, live adapters
- **Backtest** (`trading-backtest`) — deterministic tick replay
- **Strategies** (`packages/strategies/*`) — pluggable alpha; validate multiple modes in parallel
- **App** (`trading-app`) — Windows integrator, config, storage, reporting

Replaces four sibling repos (`trading-engine`, `trading-backtest`, `strategy-vwap-momentum`, `trading-app`) with one clone path. Old repos are **archived**, not deleted.

---

## 2. Directory layout

```text
tfx-trading/
├── monorepo/
│   ├── SPEC.md                 # this file — structure truth
│   └── Plan.md                 # migration checklist
├── packages/
│   ├── trading-engine/         # import: trading_engine
│   ├── trading-backtest/       # import: trading_backtest
│   └── strategies/             # all strategy plugins live here
│       ├── vwap-momentum/      # pip name: strategy-vwap-momentum
│       └── <name>/             # future: breakout, mean-revert, …
├── apps/
│   └── trading-app/            # not installable; src/ on PYTHONPATH
├── scripts/
│   ├── setup-dev.sh            # editable install all packages
│   └── run-all-tests.sh        # four test suites
├── pyproject.toml              # workspace meta (optional uv workspace)
├── README.md                   # clone + setup entry
└── .github/workflows/ci.yml
```

**Excluded**: `Shioaji/` vendor clone — use `pip install shioaji` only.

### Why `packages/strategies/`?

| Flat `packages/strategy-*` | Grouped `packages/strategies/<name>/` |
|----------------------------|----------------------------------------|
| Strategies mixed with kernel/backtest | Clear boundary: infra vs alpha |
| Harder to scan when validating N modes | Add/remove whole strategy dirs easily |
| Same pip/import names either way | Folder = short name; pip name keeps `strategy-` prefix |

**Naming rules**

| Layer | Convention | Example |
|-------|------------|---------|
| Folder | `packages/strategies/<short-kebab>/` | `vwap-momentum` |
| pip / pyproject `name` | `strategy-<short-kebab>` | `strategy-vwap-momentum` |
| Python import | `strategy_<snake>` | `strategy_vwap_momentum` |
| Entry point key | `<snake>` | `vwap_momentum` |

Module-level specs remain in each package’s own `SPEC.md` (e.g. `packages/trading-engine/SPEC.md`).

---

## 3. Dependency graph

```text
apps/trading-app
  ├── packages/trading-engine
  ├── packages/trading-backtest ──► trading-engine
  └── packages/strategies/* ──────► trading-engine
```

Strategy plugins register via setuptools entry point group `trading_engine.strategies` (unchanged from multi-repo design).

---

## 4. Install & dev

### Fresh clone (macOS / Linux / Windows)

```bash
git clone https://github.com/timhwchuang/tfx-trading.git
cd txf-trading
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
bash scripts/setup-dev.sh
```

### `scripts/setup-dev.sh` (target)

```bash
pip install -e packages/trading-engine
pip install -e packages/trading-backtest
pip install -e packages/strategies/vwap-momentum
pip install shioaji "PyYAML>=6.0"
```

### App requirements (path editable)

`apps/trading-app/requirements.txt`:

```text
-e ../../packages/trading-engine
-e ../../packages/trading-backtest
-e ../../packages/strategies/vwap-momentum
shioaji
PyYAML>=6.0
```

No `git+https://...@vX.Y.Z` pins inside monorepo.

---

## 5. Tests

```bash
bash scripts/run-all-tests.sh
```

| Package | Path | Expected count |
|---------|------|----------------|
| trading-engine | `packages/trading-engine` | ~80 |
| trading-backtest | `packages/trading-backtest` | varies |
| strategy-vwap-momentum | `packages/strategies/vwap-momentum` | ~33 |
| trading-app | `apps/trading-app` | ~81 |

---

## 6. Adding a new strategy (research / validation)

1. Copy scaffold from `packages/strategies/vwap-momentum/` → `packages/strategies/<name>/`
2. Set `pyproject.toml`:
   - `name = "strategy-<name>"`
   - `dependencies = ["trading-engine>=0.2.2,<1.0"]`
   - `[project.entry-points."trading_engine.strategies"]` → `<name> = "strategy_<module>:StrategyClass"`
3. Add to `scripts/setup-dev.sh` and `run-all-tests.sh`
4. Wire app (optional post-migration): `config.yaml` `strategy.name` + `load_named_strategy()` in live/backtest

Dropping a failed experiment: delete or move folder to `experiments/` — no separate GitHub repo to archive.

---

## 7. Versioning & release

**Per-package** `version` in each `pyproject.toml` may diverge (engine `0.2.2`, strategy `0.1.2`, …).

**Monorepo tag** (optional): single tag e.g. `v2026.06.17` or `v0.3.0-monorepo` on integration milestones.

Release SOP (replaces four-repo `UPGRADE_RUNBOOK`):

1. Change code in affected package(s)
2. Bump that package’s `version` + `CHANGELOG.md` if user-facing
3. `bash scripts/run-all-tests.sh` — all green
4. Commit; optional monorepo tag
5. No cross-repo pin matrix

---

## 8. GitHub repository metadata

Use when creating **`timhwchuang/tfx-trading`**:

### Description (pick one)

**English (recommended, ≤350 chars)**

> Monorepo for Taiwan TXF futures: trading-engine kernel, tick backtest, pluggable strategies (VWAP momentum), and Windows UAT app. Python 3.11+, Shioaji. Research / simulation — not investment advice.

**中文短版**

> 台指期 TXF 交易 monorepo：engine 狀態機、tick 回測、可插拔策略、Windows UAT 整合。Python 3.11+ / 永豐 Shioaji。個人研究用途。

### Topics (suggested)

`python`, `trading`, `futures`, `backtesting`, `shioaji`, `taiwan`, `algorithmic-trading`, `vwap`, `monorepo`

### Homepage / Documentation

- Homepage: `https://github.com/timhwchuang/tfx-trading`
- Docs entry: `monorepo/SPEC.md` and `apps/trading-app/README.md`

### Default branch

`main`

---

## 9. Archived sibling repos

After migration verified, archive (read-only, **do not delete**):

| Old repo | Redirect banner |
|----------|-----------------|
| `trading-engine` | → `txf-trading` / `packages/trading-engine` |
| `trading-backtest` | → `packages/trading-backtest` |
| `strategy-vwap-momentum` | → `packages/strategies/vwap-momentum` |
| `trading-app` | → `apps/trading-app` |

Historical tags on old repos remain installable but frozen.

---

## 10. Out of scope (Future)

- `config.yaml` dynamic `strategy.name` (loader exists; CLI not wired)
- `trading-app` as installable setuptools package
- Automatic mirror/split back to standalone repos
- `Shioaji/` vendored inside monorepo