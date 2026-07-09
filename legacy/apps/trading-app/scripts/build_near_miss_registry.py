"""Build NEAR_MISS_REGISTRY.md draft from workspace counterfactual JSON."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scripts.summarize_alpha_train import _find_train_jsons, summarize_file  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
REGISTRY = REPO / "workspaces" / "NEAR_MISS_REGISTRY.md"

NEAR_MISS_CLASSES = frozenset(
    {
        "skew_profile_fail",
        "sample_sparse",
        "near_miss_train_positive",
    }
)

APPEAL_OUTCOME_CLASSES = frozenset(
    {
        "skew_profile_fail",
        "near_miss_train_positive",
    }
)

TXF_NOTES = {
    "FT-018": "TXF 2026-06-30：near-miss 標竿 · closure_review passed · 非 champion",
    "FT-014": "n=7 · phase0 未過 · 可申訴否",
    "FT-006": "frozen k=2.0 · G1/G2 未過 · 非 near-miss",
}


def _ft_id(ws_name: str) -> str:
    mapping = {
        "gudt-baseline": "FT-018",
        "mvhp-baseline": "FT-014",
        "vsf-baseline": "FT-006",
        "sfbt-baseline": "FT-019",
        "gdc-baseline": "FT-016",
        "orb-baseline": "FT-009",
    }
    return mapping.get(ws_name, ws_name)


def build_registry_rows(*, split_2025: bool = True) -> list[dict]:
    rows: list[dict] = []
    for ws_dir in sorted((REPO / "workspaces").glob("*-baseline")):
        best: dict | None = None
        for jpath in _find_train_jsons(ws_dir):
            row = summarize_file(jpath, split_2025=split_2025)
            if not row:
                continue
            champ = row.get("champion") or {}
            nt = champ.get("net_total")
            if nt is None:
                continue
            if best is None or (nt > (best.get("champion") or {}).get("net_total", -9999)):
                best = row
        if not best:
            continue
        champ = best.get("champion") or {}
        nt = champ.get("net_total")
        oc = best.get("outcome_class") or ""
        phase0_pass = best.get("phase0_pass") is True
        if oc not in NEAR_MISS_CLASSES:
            continue
        if isinstance(nt, (int, float)) and nt <= 0:
            continue
        ws = best["file"].split("/")[1]
        ft = _ft_id(ws)
        appeal = (
            oc in APPEAL_OUTCOME_CLASSES
            and phase0_pass
            and isinstance(nt, (int, float))
            and nt > 0
        )
        rows.append(
            {
                "ft": ft,
                "workspace": ws,
                "train_net_total": nt,
                "net_mean": champ.get("net_mean"),
                "n": champ.get("n"),
                "outcome_class": oc,
                "outcome_hint": best.get("outcome_hint"),
                "appeal_eligible": appeal,
                "txf_note": TXF_NOTES.get(ft, ""),
            }
        )
    rows.sort(key=lambda r: float(r.get("train_net_total") or 0), reverse=True)
    return rows


def render_markdown(rows: list[dict]) -> str:
    today = date.today().isoformat()
    lines = [
        "# Near-Miss Registry — Alpha train 正帳面 / 次級 gate 未過",
        "",
        f"> **更新**：{today} · 工具：`python -m scripts.build_near_miss_registry`",
        "> **禁止**依本表自動 tune grid；僅供 Pick thesis / closure_review 參考。",
        "> SSOT：[`OUTCOME_REGISTRY.md`](../docs/features/ai-backtest-tuning/OUTCOME_REGISTRY.md)",
        "",
        "| FT | train net_total | n | net/趟 | outcome_class | 可申訴 | TXF 備註 |",
        "|----|----------------:|--:|-------:|---------------|:------:|----------|",
    ]
    for r in rows:
        nm = r.get("net_mean")
        nm_s = f"{nm:.2f}" if isinstance(nm, (int, float)) else "—"
        nt = r.get("train_net_total")
        nt_s = f"{nt:.1f}" if isinstance(nt, (int, float)) else "—"
        appeal = "是" if r.get("appeal_eligible") else "否"
        lines.append(
            f"| {r['ft']} | {nt_s} | {r.get('n', '—')} | {nm_s} | "
            f"`{r.get('outcome_class', '—')}` | {appeal} | {r.get('txf_note', '')} |"
        )
    lines.extend(
        [
            "",
            "## 手動補充（審計標註）",
            "",
            "| FT | 備註 |",
            "|----|------|",
            "| FT-006 k=2.5 | 事後 k 切片 · net_total +162.2 · **非** pre-register · 禁止救屍 |",
            "| FT-009 ORB | legacy 01–04 過 · 2025 全 param net 負 · 非 near-miss |",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write workspaces/NEAR_MISS_REGISTRY.md")
    parser.add_argument("--no-split-2025", action="store_true")
    args = parser.parse_args(argv)

    rows = build_registry_rows(split_2025=not args.no_split_2025)
    md = render_markdown(rows)
    print(md)
    if args.write:
        REGISTRY.write_text(md, encoding="utf-8")
        print(f"\nWrote {REGISTRY}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
