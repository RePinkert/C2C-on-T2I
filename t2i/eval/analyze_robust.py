"""Robustness analyses for the blind eval (round 2), run after analyze_votes.py.

Input : per-evaluator votes CSVs from sheet_to_votes.py
        (columns: id,prompt,q,answer,truth_left,truth_right) + prompts_v2.json (lang)
        + results/prompts_generated/pairA|B.json (raw vs enhanced text similarity)
Output: results/metrics/votes_robust.md|csv, report/figures/fig_blind_lang.png

Reports, per comparison x question:
  - vote-level counts / win rate (excluding ties and ties-as-half) / exact binomial p
  - leave-one-evaluator-out p range
  - prompt-level (cluster-robust) sign test and Wilcoxon signed-rank on per-prompt
    win fractions, because votes within a prompt are not independent
  - language split (zh/en from prompts_v2.json) with vote-level + prompt-level tests
    and a 2x2 Fisher interaction test
  - inter-rater item overlap (how many items >=2 raters, mean pairwise agreement)
  - text similarity of t2t/c2c output to the raw prompt (word-set Jaccard)

Usage: python analyze_robust.py --votes ..\results\blind\votes_*.csv
"""
import argparse
import csv
import glob
import json
import os
from collections import defaultdict

import numpy as np
from scipy import stats

ARM_ORDER = ["raw", "t2t", "c2c"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS = os.path.join(ROOT, "prompts_v2.json")
METRICS = os.path.join(ROOT, "results", "metrics")
FIGS = os.path.join(ROOT, "report", "figures")
TEXT_DIR = os.path.join(ROOT, "results", "prompts_generated")


def canon_pair(a, b):
    return (a, b) if ARM_ORDER.index(a) < ARM_ORDER.index(b) else (b, a)


def load_votes(paths):
    rows = []
    for p in paths:
        who = os.path.splitext(os.path.basename(p))[0]
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            a, b = canon_pair(r["truth_left"], r["truth_right"])
            ans = r["answer"]
            if ans == "tie":
                label = "tie"
            else:
                win_arm = r["truth_left"] if ans == "left" else r["truth_right"]
                label = f"{a}_wins" if win_arm == a else f"{b}_wins"
            rows.append({"comparison": f"{a}_vs_{b}", "q": r["q"], "item": r["id"],
                         "pid": r["id"].split("_s")[0], "evaluator": who, "label": label})
    return rows


def tally(rows, a):
    na = sum(1 for r in rows if r["label"] == f"{a}_wins")
    nb = sum(1 for r in rows if r["label"] == f"{a}_wins".replace(a, "c2c") if a != "c2c") if False else 0
    return na


def counts(rows, a, b):
    na = sum(1 for r in rows if r["label"] == f"{a}_wins")
    nb = sum(1 for r in rows if r["label"] == f"{b}_wins")
    nt = sum(1 for r in rows if r["label"] == "tie")
    return na, nb, nt


def binom_p(k, n):
    if n == 0:
        return float("nan")
    return float(stats.binomtest(k, n, 0.5).pvalue)


def fmt_p(p):
    if p != p:
        return "-"
    return "<1e-4" if p < 1e-4 else f"{p:.4f}"


def prompt_fracs(rows, a, b):
    """per prompt (pair_id prefix): win fraction of a with ties as half."""
    g = defaultdict(list)
    for r in rows:
        g[r["pid"]].append(r)
    out = {}
    for pid, rs in g.items():
        na, nb, nt = counts(rs, a, b)
        out[pid] = (na + 0.5 * nt) / (na + nb + nt)
    return out


def prompt_level_test(rows, a, b):
    fr = prompt_fracs(rows, a, b)
    vals = np.array(list(fr.values()))
    pos = int((vals > 0.5).sum())
    neg = int((vals < 0.5).sum())
    sign_p = float(stats.binomtest(pos, pos + neg, 0.5).pvalue) if pos + neg else float("nan")
    try:
        wil = float(stats.wilcoxon(vals - 0.5, zero_method="wilcox").pvalue)
    except ValueError:
        wil = float("nan")
    return {"n_prompts": len(vals), "favor_a": pos, "favor_b": neg,
            "median_frac": float(np.median(vals)), "sign_p": sign_p, "wilcoxon_p": wil}


def norm_words(s):
    out = []
    for w in "".join(ch.lower() if (ch.isalnum() or ch.isspace()) else " " for ch in s).split():
        out.append(w)
    return out


def jaccard(x, y):
    a, b = set(norm_words(x)), set(norm_words(y))
    if not a or not b:
        return float("nan")
    return len(a & b) / len(a | b)


def text_similarity(lang_of):
    rows = []
    for key in ("pairA", "pairB"):
        path = os.path.join(TEXT_DIR, f"{key}.json")
        if not os.path.exists(path):
            continue
        d = json.load(open(path, encoding="utf-8"))
        for it in d["items"]:
            raw = it["user_prompt"]
            rows.append({"pair": key, "pid": it["id"], "lang": lang_of.get(it["id"], "?"),
                         "raw_words": len(norm_words(raw)),
                         "t2t_words": len(norm_words(it["t2t"]["text"])),
                         "c2c_words": len(norm_words(it["c2c"]["text"])),
                         "jac_t2t": jaccard(raw, it["t2t"]["text"]),
                         "jac_c2c": jaccard(raw, it["c2c"]["text"])})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--votes", nargs="+", required=True)
    ap.add_argument("--out-dir", default=METRICS)
    ap.add_argument("--fig-dir", default=FIGS)
    args = ap.parse_args()

    paths = []
    for v in args.votes:
        paths.extend(sorted(glob.glob(v)) if any(c in v for c in "*?[]") else [v])
    paths = [p for p in paths if os.path.exists(p)]
    assert paths, "no votes files found"
    os.makedirs(args.out_dir, exist_ok=True)
    os.makedirs(args.fig_dir, exist_ok=True)

    lang_of = {it["id"]: it.get("lang", "?") for it in
               json.load(open(PROMPTS, encoding="utf-8"))}
    rows = load_votes(paths)
    evaluators = sorted({r["evaluator"] for r in rows})

    groups = defaultdict(list)
    for r in rows:
        groups[(r["comparison"], r["q"])].append(r)

    md, csv_rows = [], []
    md.append("# 盲评稳健性分析（聚类校正 / 分语种 / 重叠度）")
    md.append("")
    md.append(f"数据：{len(evaluators)} 份问卷、{len(rows)} 票。"
              f"票级检验把同 prompt 的重复评当作独立样本，会高估显著性，"
              f"故同时给出以 prompt 为单位的聚类校正结果。")
    md.append("")
    md.append("## 1 票级与聚类级")
    md.append("")
    md.append("| comparison | 问题 | A:B:相当 | 胜率A(排相当) | 胜率A(相当计半) | 票级 p | 留一人 p 区间 "
              "| 聚类 sign | 聚类 Wilcoxon | 聚类 A:B |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for (comp, q), g in sorted(groups.items()):
        a, b = comp.split("_vs_")
        na, nb, nt = counts(g, a, b)
        wr = na / (na + nb) if na + nb else float("nan")
        wh = (na + 0.5 * nt) / len(g)
        p = binom_p(na, na + nb)
        loo = []
        for e in evaluators:
            sub = [r for r in g if r["evaluator"] != e]
            sa, sb, _ = counts(sub, a, b)
            loo.append(binom_p(sa, sa + sb))
        loo = [x for x in loo if x == x]
        pl = prompt_level_test(g, a, b)
        md.append(f"| {comp} | {q} | {na}:{nb}:{nt} | {wr:.3f} | {wh:.3f} | {fmt_p(p)} | "
                  f"{fmt_p(min(loo))}–{fmt_p(max(loo))} | {fmt_p(pl['sign_p'])} "
                  f"({pl['favor_a']}:{pl['favor_b']}) | {fmt_p(pl['wilcoxon_p'])} | "
                  f"{pl['n_prompts']} 条 |")
        csv_rows.append({"analysis": "vote_level", "comparison": comp, "q": q,
                         "a_wins": na, "b_wins": nb, "tie": nt,
                         "winrate_excl_tie": round(wr, 4), "winrate_tie_half": round(wh, 4),
                         "binomial_p": round(p, 6),
                         "loo_p_min": round(min(loo), 6) if loo else "",
                         "loo_p_max": round(max(loo), 6) if loo else "",
                         "prompt_favor_a": pl["favor_a"], "prompt_favor_b": pl["favor_b"],
                         "prompt_sign_p": round(pl["sign_p"], 6) if pl["sign_p"] == pl["sign_p"] else "",
                         "prompt_wilcoxon_p": round(pl["wilcoxon_p"], 6) if pl["wilcoxon_p"] == pl["wilcoxon_p"] else "",
                         "n_prompts": pl["n_prompts"]})

    md.append("")
    md.append("## 2 分语种（zh = 中文输入，en = 英文输入）")
    md.append("")
    md.append("| comparison | 问题 | 语种 | A:B:相当 | 胜率A(排相当) | 票级 p | 聚类 sign | 聚类 Wilcoxon |")
    md.append("|---|---|---|---|---|---|---|---|")
    for (comp, q), g in sorted(groups.items()):
        a, b = comp.split("_vs_")
        for lang in ("zh", "en"):
            sub = [r for r in g if lang_of.get(r["pid"]) == lang]
            if not sub:
                continue
            na, nb, nt = counts(sub, a, b)
            wr = na / (na + nb) if na + nb else float("nan")
            p = binom_p(na, na + nb)
            pl = prompt_level_test(sub, a, b)
            md.append(f"| {comp} | {q} | {lang} | {na}:{nb}:{nt} | {wr:.3f} | {fmt_p(p)} | "
                      f"{fmt_p(pl['sign_p'])} ({pl['favor_a']}:{pl['favor_b']}) | "
                      f"{fmt_p(pl['wilcoxon_p'])} |")
            csv_rows.append({"analysis": f"lang_{lang}", "comparison": comp, "q": q,
                             "a_wins": na, "b_wins": nb, "tie": nt,
                             "winrate_excl_tie": round(wr, 4),
                             "binomial_p": round(p, 6),
                             "prompt_sign_p": round(pl["sign_p"], 6) if pl["sign_p"] == pl["sign_p"] else "",
                             "prompt_wilcoxon_p": round(pl["wilcoxon_p"], 6) if pl["wilcoxon_p"] == pl["wilcoxon_p"] else "",
                             "n_prompts": pl["n_prompts"]})
        # interaction
        zh = [r for r in g if lang_of.get(r["pid"]) == "zh"]
        en = [r for r in g if lang_of.get(r["pid"]) == "en"]
        if zh and en:
            za, zb, _ = counts(zh, a, b)
            ea, eb, _ = counts(en, a, b)
            try:
                _, fi = stats.fisher_exact([[za, zb], [ea, eb]])
            except ValueError:
                fi = float("nan")
            md.append(f"| {comp} | {q} | 交互(Fisher) | zh {za}:{zb} vs en {ea}:{eb} | - | "
                      f"{fmt_p(fi)} | - | - |")

    md.append("")
    md.append("## 3 跨受访者 item 重叠（κ 可行性）")
    md.append("")
    md.append("| comparison | 问题 | 独立 item | ≥2 人共评的 item | 平均两两一致率 |")
    md.append("|---|---|---|---|---|")
    for (comp, q), g in sorted(groups.items()):
        per_item = defaultdict(dict)
        for r in g:
            per_item[r["item"]][r["evaluator"]] = r["label"]
        multi = {k: v for k, v in per_item.items() if len(v) >= 2}
        agrees, pairs = 0, 0
        for v in multi.values():
            keys = list(v)
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    pairs += 1
                    if v[keys[i]] == v[keys[j]]:
                        agrees += 1
        md.append(f"| {comp} | {q} | {len(per_item)} | {len(multi)} | "
                  f"{(agrees / pairs):.3f} |" if pairs else
                  f"| {comp} | {q} | {len(per_item)} | {len(multi)} | - |")

    sim = text_similarity(lang_of)
    if sim:
        md.append("")
        md.append("## 4 增强文本与原 prompt 的相似度（pairA）")
        md.append("")
        md.append("| 语种 | prompt 数 | raw 词数 | t2t 词数 | c2c 词数 | Jaccard(raw,t2t) | Jaccard(raw,c2c) |")
        md.append("|---|---|---|---|---|---|---|")
        pa = [s for s in sim if s["pair"] == "pairA"]
        for lang in ("zh", "en"):
            sub = [s for s in pa if s["lang"] == lang]
            if not sub:
                continue
            md.append(f"| {lang} | {len(sub)} | "
                      f"{np.mean([s['raw_words'] for s in sub]):.1f} | "
                      f"{np.mean([s['t2t_words'] for s in sub]):.1f} | "
                      f"{np.mean([s['c2c_words'] for s in sub]):.1f} | "
                      f"{np.nanmean([s['jac_t2t'] for s in sub]):.3f} | "
                      f"{np.nanmean([s['jac_c2c'] for s in sub]):.3f} |")
        for lang in ("zh", "en"):
            sub = [s for s in pa if s["lang"] == lang]
            for s in sub:
                csv_rows.append({"analysis": "text_similarity", "comparison": "pairA",
                                 "q": lang, "a_wins": "", "b_wins": "", "tie": "",
                                 "winrate_excl_tie": "", "binomial_p": "",
                                 "prompt_sign_p": "", "prompt_wilcoxon_p": "",
                                 "n_prompts": "",
                                 "prompt_id": s["pid"], "raw_words": s["raw_words"],
                                 "t2t_words": s["t2t_words"], "c2c_words": s["c2c_words"],
                                 "jac_t2t": round(s["jac_t2t"], 4),
                                 "jac_c2c": round(s["jac_c2c"], 4)})

    out_md = os.path.join(args.out_dir, "votes_robust.md")
    open(out_md, "w", encoding="utf-8").write("\n".join(md) + "\n")
    out_csv = os.path.join(args.out_dir, "votes_robust.csv")
    fields = ["analysis", "comparison", "q", "a_wins", "b_wins", "tie",
              "winrate_excl_tie", "winrate_tie_half", "binomial_p", "loo_p_min",
              "loo_p_max", "prompt_favor_a", "prompt_favor_b", "prompt_sign_p",
              "prompt_wilcoxon_p", "n_prompts", "prompt_id", "raw_words",
              "t2t_words", "c2c_words", "jac_t2t", "jac_c2c"]
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in csv_rows:
            w.writerow(r)
    print(out_md)
    print(out_csv)

    # figure: overall win rate + zh/en split
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
    plt.rcParams["axes.unicode_minus"] = False
    comps = sorted({k[0] for k in groups})
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.4))
    qcolor = {"faith": "#4c72b0", "look": "#dd8452"}

    ax = axes[0]
    w = 0.36
    for j, (q, qlabel) in enumerate((("faith", "忠实度"), ("look", "观感"))):
        for i, comp in enumerate(comps):
            g = groups.get((comp, q), [])
            if not g:
                continue
            a, b = comp.split("_vs_")
            na, nb, nt = counts(g, a, b)
            rate = na / (na + nb) if na + nb else 0
            ax.bar(i + (j - 0.5) * w, rate, width=w * 0.92, color=qcolor[q],
                   label=qlabel if i == 0 else None)
            stars = "" if binom_p(na, na + nb) >= 0.05 else " *"
            ax.text(i + (j - 0.5) * w, rate + 0.02,
                    f"{na}:{nb}\np={binom_p(na, na + nb):.3f}{stars}",
                    ha="center", fontsize=7)
    ax.axhline(0.5, color="#999", ls="--", lw=1)
    ax.set_xticks(range(len(comps)), [c.replace("_vs_", " vs ") for c in comps], fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("前者胜率（排除相当）")
    ax.set_title("整体（n=11 份问卷，462 票）")
    ax.legend(fontsize=8, frameon=False, loc="upper right")

    ax = axes[1]
    w = 0.36
    for j, (lang, langlabel) in enumerate((("zh", "中文输入"), ("en", "英文输入"))):
        for i, comp in enumerate(comps):
            g = [r for r in groups.get((comp, "look"), [])
                 if lang_of.get(r["pid"]) == lang]
            if not g:
                continue
            a, b = comp.split("_vs_")
            na, nb, nt = counts(g, a, b)
            rate = na / (na + nb) if na + nb else 0
            ax.bar(i + (j - 0.5) * w, rate, width=w * 0.92,
                   color="#4c72b0" if lang == "zh" else "#937860",
                   label=langlabel if i == 0 else None)
            ax.text(i + (j - 0.5) * w, rate + 0.02,
                    f"{na}:{nb}\np={binom_p(na, na + nb):.3f}", ha="center", fontsize=7)
    ax.axhline(0.5, color="#999", ls="--", lw=1)
    ax.set_xticks(range(len(comps)), [c.replace("_vs_", " vs ") for c in comps], fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("前者胜率（观感，排除相当）")
    ax.set_title("分语种（观感）：raw 的优势集中在中文输入")
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(args.fig_dir, "fig_blind_lang.png"), dpi=150)
    plt.close(fig)
    print(os.path.join(args.fig_dir, "fig_blind_lang.png"))


if __name__ == "__main__":
    main()
