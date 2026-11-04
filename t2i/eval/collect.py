"""Collect experiment artifacts into a manifest CSV + text-stats CSV.

Scans ComfyUI output dir exp_v2/{prefix}{pid}_s{seed}/{arm}_*.png and joins
with results/prompts_generated/{pair}.json texts. Writes
results/metrics/manifest.csv and text_stats.csv.

Usage:
  python collect.py --texts pairA.json pairB.json \
      --matrices A_moss_:pairA:moss B_moss_:pairB:moss A_krea2_:pairA:krea2
"""
import argparse
import csv
import glob
import json
import os

PLAYGROUND = os.environ.get("PLAYGROUND", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMFY_OUT = os.environ.get("COMFY_OUT", os.path.join(PLAYGROUND, "results", "exp_v2"))
OUT_DIR = os.path.join(PLAYGROUND, "results", "metrics")


def find_image(tag, arm):
    hits = sorted(glob.glob(os.path.join(COMFY_OUT, tag, f"{arm}_*.png")))
    return hits[0] if hits else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", nargs="+", required=True,
                    help="pair text JSON files from bridge --batch-file")
    ap.add_argument("--matrices", nargs="+", default=[":pairA:moss"],
                    help="prefix:pairkey:backend[:pid-range], "
                         "pid-range like p01-p08 or p01,p02 (default all)")
    ap.add_argument("--seeds", default="42,1042,2042")
    ap.add_argument("--prompt-ids", default="all")
    ap.add_argument("--label", default="", help="extra column value (e.g. exp group)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    seeds = [int(s) for s in args.seeds.split(",")]
    keep = None if args.prompt_ids == "all" else set(args.prompt_ids.split(","))

    texts = {}
    for tpath in args.texts:
        data = json.load(open(tpath, encoding="utf-8"))
        key = os.path.splitext(os.path.basename(tpath))[0]
        texts[key] = data

    manifest_rows, text_rows = [], []
    for mat in args.matrices:
        parts = mat.split(":")
        prefix, pair_key, backend = parts[:3]
        pid_spec = parts[3] if len(parts) > 3 else ""
        if pid_spec:
            if "-" in pid_spec:
                lo, hi = pid_spec.split("-")
                pids = [f"p{i:02d}" for i in range(int(lo[1:]), int(hi[1:]) + 1)]
            else:
                pids = pid_spec.split(",")
        else:
            pids = None
        data = texts[pair_key]
        pair = data.get("pair", pair_key)
        for it in data["items"]:
            pid = it["id"]
            if keep and pid not in keep:
                continue
            if pids and pid not in pids:
                continue
            user_prompt = it["user_prompt"]
            arms_text = {"raw": user_prompt,
                         "t2t": it.get("t2t", {}).get("text", ""),
                         "c2c": it.get("c2c", {}).get("text", "")}
            for arm in ("t2t", "c2c"):
                st = it.get(arm, {}).get("text_stats", {})
                text_rows.append({
                    "pair": pair, "backend": backend, "prompt_id": pid, "arm": arm,
                    "seconds": it.get(arm, {}).get("total_seconds"), **st,
                    "n_chars": len(arms_text[arm]),
                    "text": arms_text[arm].replace("\n", " "),
                })
            for seed in seeds:
                tag = f"{prefix}{pid}_s{seed}"
                for arm in ("raw", "t2t", "c2c"):
                    manifest_rows.append({
                        "tag": tag, "prompt_id": pid, "seed": seed, "arm": arm,
                        "pair": pair, "backend": backend,
                        "image_path": find_image(tag, arm),
                        "user_prompt": user_prompt,
                        "enhanced_prompt": arms_text[arm].replace("\n", " "),
                    })

    with open(os.path.join(OUT_DIR, "manifest.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
        w.writeheader()
        w.writerows(manifest_rows)
    with open(os.path.join(OUT_DIR, "text_stats.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(text_rows[0].keys()))
        w.writeheader()
        w.writerows(text_rows)
    missing = sum(1 for r in manifest_rows if not r["image_path"])
    print(f"manifest rows: {len(manifest_rows)} (missing images: {missing})")
    print(f"text rows: {len(text_rows)}")
    print(os.path.join(OUT_DIR, "manifest.csv"))


if __name__ == "__main__":
    main()
