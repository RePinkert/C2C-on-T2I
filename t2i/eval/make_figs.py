"""Render report figures from metrics CSVs into report/figures/.

Outputs:
  fig_latency.png       text-stage latency (cold-start + steady-state) per pair
  fig_quality.png       boxplots (3 matrices x 3 metrics) with significance stars
  fig_degenerate.png    rep-4gram / distinct-2 by arm + degenerate counts
  fig_blind.png         blind-eval win rates (only if votes_summary.csv exists)
  gallery/              labeled images of degenerate cases

Usage: python make_figs.py
"""
import csv
import json
import os
import shutil
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

PLAYGROUND = r"C:\Yet\Playground"
METRICS = os.path.join(PLAYGROUND, "results", "metrics")
FIGS = os.path.join(PLAYGROUND, "report", "figures")
COMFY_OUT = r"C:\Yet\Playground\exp_v2"

MATRIX_LABEL = {
    ("qwen3_0.6b+qwen2.5_0.5b", "moss"): "主矩阵 pairA@moss (n=84)",
    ("qwen3_0.6b+qwen3_4b_base", "moss"): "泛化A pairB@moss (n=24)",
    ("qwen3_0.6b+qwen2.5_0.5b", "krea2"): "泛化B pairA@krea2 (n=24)",
}
PAIR_LABEL = {
    "qwen3_0.6b+qwen2.5_0.5b": "pairA (0.6B+0.5B)",
    "qwen3_0.6b+qwen3_4b_base": "pairB (0.6B+4B)",
}
METRIC_LABEL = {"clip_user": "CLIP score vs user prompt",
                "clip_enhanced": "CLIP score vs enhanced prompt",
                "aesthetic": "LAION aesthetic V2"}


def load_csv(name):
    return list(csv.DictReader(open(os.path.join(METRICS, name), encoding="utf-8-sig")))


def load_text_json():
    """Text-side rows from bridge batch JSONs (full 16 prompts per pair)."""
    rows = []
    for key in ("pairA", "pairB"):
        d = json.load(open(os.path.join(
            PLAYGROUND, "results", "prompts_generated", f"{key}.json"),
            encoding="utf-8"))
        pair = d["pair"]
        for it in d["items"]:
            for arm in ("t2t", "c2c"):
                st = it[arm]["text_stats"]
                rows.append({"pair": pair, "prompt_id": it["id"], "arm": arm,
                             "seconds": str(it[arm]["total_seconds"]),
                             "n_tokens": str(st["n_tokens"]),
                             "rep_4gram_max_ratio": str(st["rep_4gram_max_ratio"]),
                             "degenerate": str(st.get("degenerate", False))})
    return rows


def stars(p):
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"


def fig_latency(text_rows):
    pairs = sorted({r["pair"] for r in text_rows})
    fig, axes = plt.subplots(1, len(pairs), figsize=(9, 3.6), squeeze=False)
    for ax, pair in zip(axes[0], pairs):
        data = {"t2t": [], "c2c": []}
        for r in text_rows:
            if r["pair"] == pair and r.get("seconds"):
                data[r["arm"]].append(float(r["seconds"]))
        xs = np.arange(2)
        means = [np.mean(data[a]) for a in ("t2t", "c2c")]
        stds = [np.std(data[a]) for a in ("t2t", "c2c")]
        bars = ax.bar(xs, means, yerr=stds, capsize=4,
                      color=["#4c72b0", "#dd8452"], width=0.55)
        for x, m in zip(xs, means):
            ax.text(x, m + max(stds) * 0.2 + 0.15, f"{m:.2f}s",
                    ha="center", fontsize=10)
        ax.set_xticks(xs, ["T2T (文本中转)", "C2C (KV 融合)"])
        ax.set_ylabel("文本环节延迟 (s, 稳态均值±std)")
        ax.set_title(PAIR_LABEL.get(pair, pair))
        ax.set_ylim(0, max(means) * 1.5)
        ratio = means[0] / means[1] if means[1] else float("nan")
        ax.text(0.5, 0.92, f"加速 {ratio:.2f}x", transform=ax.transAxes,
                ha="center", fontsize=10, color="#c44")
    fig.suptitle("文本生成环节延迟（T2T vs C2C）")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_latency.png"), dpi=150)
    plt.close(fig)


def fig_quality(img_rows, stat_rows):
    matrices = [("qwen3_0.6b+qwen2.5_0.5b", "moss"),
                ("qwen3_0.6b+qwen3_4b_base", "moss"),
                ("qwen3_0.6b+qwen2.5_0.5b", "krea2")]
    metrics = ["clip_user", "clip_enhanced", "aesthetic"]
    stat = {(r["matrix"], r["metric"], r["a"], r["b"]): r for r in stat_rows}
    fig, axes = plt.subplots(3, 3, figsize=(12, 10))
    for i, (pair, backend) in enumerate(matrices):
        matrix = f"{pair}@{backend}"
        rows = [r for r in img_rows
                if r["pair"] == pair and r.get("backend") == backend]
        for j, m in enumerate(metrics):
            ax = axes[i][j]
            vals = {"raw": [], "t2t": [], "c2c": []}
            for r in rows:
                if r.get(m):
                    vals[r["arm"]].append(float(r[m]))
            bp = ax.boxplot([vals[a] for a in ("raw", "t2t", "c2c")],
                            tick_labels=["raw", "t2t", "c2c"],
                            patch_artist=True, widths=0.55)
            for patch, color in zip(bp["boxes"], ["#8c8c8c", "#4c72b0", "#dd8452"]):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)
            # 顶部留白放置三行显著性注释，避免压在箱线上
            lo, hi = ax.get_ylim()
            ax.set_ylim(lo, hi + (hi - lo) * 0.42)
            for k, (a, b) in enumerate([("raw", "t2t"), ("raw", "c2c"), ("t2t", "c2c")]):
                r = stat.get((matrix, m, a, b))
                if r:
                    ax.text(0.5, 0.985 - 0.088 * k,
                            f"{a} vs {b}: {stars(float(r['wilcoxon_p']))}",
                            transform=ax.transAxes, ha="center", va="top", fontsize=8)
            if i == 0:
                ax.set_title(METRIC_LABEL[m], fontsize=10)
            if j == 0:
                ax.set_ylabel(MATRIX_LABEL.get((pair, backend), matrix), fontsize=9)
    fig.suptitle("图像质量指标（配对 Wilcoxon 显著性：ns / * p<.05 / ** p<.01 / *** p<.001）")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_quality.png"), dpi=150)
    plt.close(fig)


def fig_degenerate(text_rows):
    pairs = sorted({r["pair"] for r in text_rows})
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    ax = axes[0]
    pos, labels, data = 0, [], []
    colors = []
    for pair in pairs:
        for arm in ("t2t", "c2c"):
            vals = [float(r["rep_4gram_max_ratio"]) for r in text_rows
                    if r["pair"] == pair and r["arm"] == arm and r.get("rep_4gram_max_ratio")]
            data.append(vals)
            labels.append(f"{PAIR_LABEL.get(pair, pair)[:6]}\n{arm}")
            colors.append("#4c72b0" if arm == "t2t" else "#dd8452")
            pos += 1
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, widths=0.55)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.set_ylabel("rep-4gram max ratio")
    ax.set_title("文本重复退化程度（按 arm × pair）")

    ax = axes[1]
    counts = defaultdict(int)
    for r in text_rows:
        counts[(PAIR_LABEL.get(r["pair"], r["pair"])[:6], r["arm"])] += (
            1 if r.get("degenerate") in ("True", "true", "1") else 0)
    keys = sorted(counts)
    xs = np.arange(len(keys))
    ax.bar(xs, [counts[k] for k in keys],
           color=["#4c72b0" if k[1] == "t2t" else "#dd8452" for k in keys], width=0.55)
    ax.set_xticks(xs, [f"{k[0]}\n{k[1]}" for k in keys])
    ax.set_ylabel("退化样本数")
    ax.set_title("退化样本计数（degenerate flag）")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_degenerate.png"), dpi=150)
    plt.close(fig)


def fig_blind():
    path = os.path.join(METRICS, "votes_summary.csv")
    if not os.path.exists(path):
        print("votes_summary.csv not found -> skip fig_blind.png")
        return
    rows = load_csv("votes_summary.csv")
    rows = [r for r in rows if r["q"] == "faith"] + [r for r in rows if r["q"] == "look"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    xs = np.arange(len(rows))
    wr = [float(r["winrate_excl_tie"]) for r in rows]
    comps = [f"{r['comparison']}\n{r['q']}" for r in rows]
    ax.bar(xs, wr, color=["#4c72b0" if "faith" in c else "#dd8452" for c in comps],
           width=0.55)
    ax.axhline(0.5, color="#999", ls="--", lw=1)
    for x, r in zip(xs, rows):
        a = r["comparison"].split("_vs_")[0]
        ax.text(x, float(r["winrate_excl_tie"]) + 0.02,
                f"{a} {float(r['winrate_excl_tie']):.0%}\np={float(r['binomial_p']):.3f}",
                ha="center", fontsize=8)
    ax.set_xticks(xs, comps)
    ax.set_ylim(0, 1)
    ax.set_ylabel("胜率（排除相当）")
    ax.set_title("人工盲评胜率（排除“相当”）")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_blind.png"), dpi=150)
    plt.close(fig)


def gallery(text_rows, img_rows):
    gdir = os.path.join(FIGS, "gallery")
    os.makedirs(gdir, exist_ok=True)
    seen = set()
    for r in text_rows:
        if r.get("degenerate") not in ("True", "true", "1"):
            continue
        key = (r["pair"], r["prompt_id"])
        if key in seen:
            continue
        seen.add(key)
        match = [x for x in img_rows
                 if x["pair"] == r["pair"] and x["prompt_id"] == r["prompt_id"]
                 and x["seed"] == "42" and x["arm"] == "c2c" and x["image_path"]]
        if not match:
            continue
        tag = match[0]["tag"]
        src = os.path.join(COMFY_OUT, tag.replace("_s42", "_s42"), "labeled_00001_.png")
        if not os.path.exists(src):
            continue
        pair_short = "pairA" if "2.5_0.5b" in r["pair"] else "pairB"
        dst = os.path.join(gdir, f"{pair_short}_{r['prompt_id']}_s42_labeled.png")
        shutil.copy(src, dst)
        print("gallery <-", dst)


def main():
    os.makedirs(FIGS, exist_ok=True)
    text_rows = load_text_json()
    img_rows = load_csv("image_metrics.csv")
    stat_rows = load_csv("stats_pairs.csv")
    fig_latency(text_rows)
    fig_quality(img_rows, stat_rows)
    fig_degenerate(text_rows)
    fig_blind()
    gallery(text_rows, img_rows)
    print("figures ->", FIGS)


if __name__ == "__main__":
    main()
