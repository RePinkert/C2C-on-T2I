"""Convert a Google Sheet export of blind-eval submissions into per-evaluator votes CSVs.

Input : the `blind_votes` sheet exported as CSV, columns
        submission_id,seq,submitted_at,nickname,pair_id,q,answer,truth_left,truth_right
Output: one votes_<seq>_<nickname>.csv per submission, columns
        id,prompt,q,answer,truth_left,truth_right   (same schema analyze_votes.py expects)

The prompt text is looked up from prompts_v2.json by pair_id (e.g. p01_s42 -> p01).

Usage:
  python sheet_to_votes.py --sheet ..\\results\\blind\\sheet_votes.csv \\
      --out-dir ..\\results\\blind
"""
import argparse
import csv
import json
import os
import re
from collections import defaultdict

PROMPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "prompts_v2.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True, help="CSV export of the blind_votes sheet")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--prompts", default=PROMPTS)
    args = ap.parse_args()

    prompt_by_pid = {}
    if os.path.exists(args.prompts):
        for it in json.load(open(args.prompts, encoding="utf-8")):
            prompt_by_pid[it["id"]] = it["prompt"]

    rows = list(csv.DictReader(open(args.sheet, encoding="utf-8-sig")))
    groups = defaultdict(list)
    meta = {}
    for r in rows:
        sid = (r.get("submission_id") or "").strip()
        if not sid:
            continue
        groups[sid].append(r)
        meta.setdefault(sid, (r.get("seq", ""), r.get("nickname", ""), r.get("submitted_at", "")))

    os.makedirs(args.out_dir, exist_ok=True)
    written = []
    for sid, rs in sorted(groups.items(), key=lambda kv: (int(meta[kv[0]][0] or 0), kv[0])):
        seq, nick, _ = meta[sid]
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"votes_{seq}_{nick or 'anon'}") + ".csv"
        out_path = os.path.join(args.out_dir, name)
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "prompt", "q", "answer", "truth_left", "truth_right"])
            for r in rs:
                pair_id = (r.get("pair_id") or "").strip()
                pid = pair_id.split("_s")[0]
                w.writerow([pair_id, prompt_by_pid.get(pid, ""), r.get("q", ""),
                            r.get("answer", ""), r.get("truth_left", ""), r.get("truth_right", "")])
        written.append((name, len(rs), nick))
        print(f"{name}: {len(rs)} votes")

    print(f"\n{len(written)} submissions -> {args.out_dir}")
    bad = [w for w in written if w[1] != 42]
    if bad:
        print("WARNING: submissions with != 42 rows:",
              ", ".join(f"{n}({c})" for n, c, _ in bad))


if __name__ == "__main__":
    main()
