"""Aggregate blind-eval votes from multiple evaluators.

Reads one or more votes CSVs exported from make_blind_html.py pages
(columns: id,prompt,q,answer,truth_left,truth_right), maps each vote to the
winning arm, and reports per comparison x question:
  - win counts/rates (two conventions: excluding ties / ties counted as 0.5)
  - two-sided exact binomial test on non-tie votes
  - inter-evaluator agreement (pairwise Cohen's kappa, >=2 evaluators)

The comparison (which arm pair a page tested) is inferred from the truth
columns, so CSVs from different pages can be mixed in one call.

Usage:
  python analyze_votes.py --votes ..\\results\\blind\\votes_*.csv \
      --out-dir ..\\results\\metrics
"""
import argparse
import csv
import glob
import itertools
import os
from collections import defaultdict

from scipy import stats

ARM_ORDER = ["raw", "t2t", "c2c"]


def canon_pair(a, b):
    return (a, b) if ARM_ORDER.index(a) < ARM_ORDER.index(b) else (b, a)


def load_votes(paths):
    """rows: (comparison, q, item, evaluator, label) with label in
    {a_wins, b_wins, tie} relative to the canonical arm order."""
    rows = []
    for p in paths:
        who = os.path.splitext(os.path.basename(p))[0]
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            la, lb = r["truth_left"], r["truth_right"]
            a, b = canon_pair(la, lb)
            ans = r["answer"]
            if ans == "tie":
                label = "tie"
            else:
                win_arm = la if ans == "left" else lb
                label = f"{a}_wins" if win_arm == a else f"{b}_wins"
            rows.append({"comparison": f"{a}_vs_{b}", "q": r["q"],
                         "item": r["id"], "evaluator": who, "label": label})
    return rows


def cohens_kappa(pairs):
    """pairs: list of (label1, label2)."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    cats = {c for p in pairs for c in p}
    po = sum(1 for x, y in pairs if x == y) / n
    pe = sum((sum(1 for x, _ in pairs if x == c) / n) *
             (sum(1 for _, y in pairs if y == c) / n) for c in cats)
    if pe >= 1:
        return float("nan")
    return (po - pe) / (1 - pe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--votes", nargs="+", required=True)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    paths = []
    for v in args.votes:
        paths.extend(sorted(glob.glob(v)) if any(ch in v for ch in "*?[]") else [v])
    paths = [p for p in paths if os.path.exists(p)]
    assert paths, "no votes files found"
    out_dir = args.out_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "metrics")
    os.makedirs(out_dir, exist_ok=True)

    rows = load_votes(paths)
    evaluators = sorted({r["evaluator"] for r in rows})
    groups = defaultdict(list)
    for r in rows:
        groups[(r["comparison"], r["q"])].append(r)

    out_rows, lines = [], []
    lines.append("# 盲评汇总")
    lines.append("")
    lines.append(f"评估者（{len(evaluators)}）：{', '.join(evaluators)}")
    lines.append("")
    lines.append("| comparison | 问题 | 有效票 | A 胜 | B 胜 | 相当 | "
                 "胜率A(排相当) | 胜率A(相当计半) | binomial p | mean κ |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for (comp, q), g in sorted(groups.items()):
        a, b = comp.split("_vs_")
        na = sum(1 for r in g if r["label"] == f"{a}_wins")
        nb = sum(1 for r in g if r["label"] == f"{b}_wins")
        nt = sum(1 for r in g if r["label"] == "tie")
        n_eff = na + nb
        wr_excl = na / n_eff if n_eff else float("nan")
        wr_half = (na + 0.5 * nt) / len(g) if g else float("nan")
        p = stats.binomtest(na, n_eff, 0.5).pvalue if n_eff else float("nan")
        kappas = []
        for e1, e2 in itertools.combinations(evaluators, 2):
            m = defaultdict(dict)
            for r in g:
                if r["evaluator"] in (e1, e2):
                    m[r["item"]][r["evaluator"]] = r["label"]
            pairs = [(v[e1], v[e2]) for v in m.values() if e1 in v and e2 in v]
            if pairs:
                kappas.append(cohens_kappa(pairs))
        mk = (sum(kappas) / len(kappas)) if kappas else float("nan")
        out_rows.append({
            "comparison": comp, "q": q, "n": len(g),
            f"{a}_wins": na, f"{b}_wins": nb, "tie": nt,
            "winrate_excl_tie": round(wr_excl, 4),
            "winrate_tie_half": round(wr_half, 4),
            "binomial_p": round(float(p), 6),
            "mean_kappa": "" if mk != mk else round(mk, 4),
            "n_evaluators": len(evaluators),
        })
        lines.append(
            f"| {comp} | {q} | {len(g)} | {na} | {nb} | {nt} | "
            f"{wr_excl:.3f} | {wr_half:.3f} | {p:.4f} | "
            f"{'-' if mk != mk else f'{mk:.3f}'} |")

    per_eval = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        a, b = r["comparison"].split("_vs_")
        slot = per_eval[(r["comparison"], r["q"], r["evaluator"])]
        if r["label"] == f"{a}_wins":
            slot[0] += 1
        elif r["label"] == f"{b}_wins":
            slot[1] += 1
        else:
            slot[2] += 1
    lines.append("")
    lines.append("## 分评估者明细（A 胜 / B 胜 / 相当）")
    lines.append("")
    lines.append("| comparison | 问题 | 评估者 | A 胜 | B 胜 | 相当 |")
    lines.append("|---|---|---|---|---|---|")
    for (comp, q, who), (na, nb, nt) in sorted(per_eval.items()):
        lines.append(f"| {comp} | {q} | {who} | {na} | {nb} | {nt} |")

    out_csv = os.path.join(out_dir, "votes_summary.csv")
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    out_md = os.path.join(out_dir, "votes_summary.md")
    open(out_md, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(out_csv)
    print(out_md)


if __name__ == "__main__":
    main()
