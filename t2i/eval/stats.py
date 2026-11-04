"""Paired statistics for the C2C experiment: Wilcoxon + bootstrap CI + effect size.

Reads results/metrics/image_metrics.csv (and optionally text_stats.csv).
Writes results/metrics/stats_summary.md and stats_pairs.csv.
"""
import argparse
import csv
import itertools
import os
from collections import defaultdict

import numpy as np
from scipy import stats


def paired_report(a, b, name_a, name_b, metric):
    a, b = np.asarray(a, float), np.asarray(b, float)
    mask = np.isfinite(a) & np.isfinite(b)
    a, b = a[mask], b[mask]
    n = len(a)
    if n < 6:
        return None
    diff = a - b
    try:
        w_stat, p = stats.wilcoxon(a, b, alternative="two-sided")
    except ValueError:
        w_stat, p = float("nan"), float("nan")
    rng = np.random.default_rng(42)
    boots = [rng.choice(diff, n, replace=True).mean() for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    rb = 1 - (2 * w_stat) / (n * (n + 1)) if np.isfinite(w_stat) else float("nan")
    return {
        "metric": metric, "a": name_a, "b": name_b, "n": n,
        "mean_a": round(a.mean(), 4), "mean_b": round(b.mean(), 4),
        "mean_diff": round(diff.mean(), 4),
        "ci95_lo": round(lo, 4), "ci95_hi": round(hi, 4),
        "wilcoxon_p": round(float(p), 6), "rank_biserial": round(float(rb), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True, help="image_metrics.csv")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    out_dir = args.out_dir or os.path.dirname(args.metrics)

    rows = list(csv.DictReader(open(args.metrics, encoding="utf-8-sig")))
    by = defaultdict(dict)  # (pair, backend, prompt_id, seed) -> arm -> {metric: val}
    for r in rows:
        key = (r.get("pair", ""), r.get("backend", ""), r["prompt_id"], r["seed"])
        for m in ("clip_user", "clip_enhanced", "aesthetic"):
            v = r.get(m, "")
            by[key].setdefault(r["arm"], {})[m] = (
                float(v) if v not in ("", None) else float("nan"))

    matrices = sorted({(k[0], k[1]) for k in by})
    reports = []
    for pair, backend in matrices:
        keys = sorted(k for k in by if (k[0], k[1]) == (pair, backend))
        matrix = f"{pair}@{backend}"
        for m in ("clip_user", "clip_enhanced", "aesthetic"):
            for arm_a, arm_b in itertools.combinations(["raw", "t2t", "c2c"], 2):
                vals_a, vals_b = [], []
                for key in keys:
                    if arm_a in by[key] and arm_b in by[key]:
                        vals_a.append(by[key][arm_a].get(m, float("nan")))
                        vals_b.append(by[key][arm_b].get(m, float("nan")))
                rep = paired_report(vals_a, vals_b, arm_a, arm_b, m)
                if rep:
                    rep["matrix"] = matrix
                    reports.append(rep)

    out_csv = os.path.join(out_dir, "stats_pairs.csv")
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(reports[0].keys()))
        w.writeheader()
        w.writerows(reports)

    lines = ["# 统计汇总（配对 Wilcoxon + bootstrap 95% CI）", ""]
    lines.append("| matrix | metric | 对比 | n | mean A | mean B | diff | 95% CI | p | rank-biserial |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in reports:
        sig = "**" if r["wilcoxon_p"] < 0.05 else ""
        lines.append(
            f"| {r['matrix']} | {r['metric']} | {r['a']} vs {r['b']} | {r['n']} | {r['mean_a']} | "
            f"{r['mean_b']} | {sig}{r['mean_diff']}{sig} | "
            f"[{r['ci95_lo']}, {r['ci95_hi']}] | {sig}{r['wilcoxon_p']}{sig} | "
            f"{r['rank_biserial']} |")
    out_md = os.path.join(out_dir, "stats_summary.md")
    open(out_md, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(out_csv)
    print(out_md)


if __name__ == "__main__":
    main()
