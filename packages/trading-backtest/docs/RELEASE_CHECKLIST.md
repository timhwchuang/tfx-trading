# Release checklist — v0.1.0 (public tag)

Use this before tagging `v0.1.0` on GitHub.

## Pre-tag verification

- [ ] `python3 run_tests.py` — all tests pass (currently 25+)
- [ ] `ruff check src tests` — no lint errors
- [ ] `ruff format --check src tests` — formatted
- [ ] `README.md` / `SPEC.md` / `docs/releases/v0.1.0.md` — no broken in-repo links
- [ ] `pyproject.toml` `Documentation` URL → `SPEC.md`
- [ ] `src/trading_backtest/_version.py` matches tag (`0.1.0`)
- [ ] `CHANGELOG.md` date and `[0.1.0]` link ready
- [ ] No committed `*.egg-info/` or `.ruff_cache/` (see `.gitignore`); remove local artifacts before tag:
  ```bash
  rm -rf src/*.egg-info .ruff_cache
  git ls-files '*.egg-info'  # should print nothing
  ```

## Dependency pin (document in release)

Consumers must pin:

```bash
pip install "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.0"
pip install "trading-backtest @ git+https://github.com/timhwchuang/trading-backtest.git@v0.1.0"
```

## Tag & publish

```bash
git add -A
git commit -m "Release v0.1.0: standalone spec, validation tools, public research alpha"
git tag -a v0.1.0 -m "v0.1.0 — deterministic backtest driver (research alpha)"
git remote add origin https://github.com/timhwchuang/trading-backtest.git  # if needed
git push origin main
git push origin v0.1.0
```

## Post-tag

- [ ] GitHub Release notes — copy from `docs/releases/v0.1.0.md`
- [ ] Verify CI green on `main` after push
- [ ] Update workspace `docs/three-repo/README.md` Backtest status → ✅ *(internal monorepo only)*
- [ ] Notify collaborators: **research alpha**, not production execution simulator

## Scope reminder (do not oversell)

v0.1.0 is suitable for:

- Strategy state-machine validation on the same `TradingEngine` kernel
- Determinism regression and param sweep
- Internal / collaborator research with documented limitations

v0.1.0 is **not** suitable as sole evidence for:

- Go-live decisions from backtest PnL alone
- External UAT sign-off without paper-trade fill comparison