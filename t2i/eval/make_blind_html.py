"""Generate a local blind-eval HTML page from the manifest.

Pairs arms per (prompt_id, seed), randomizes left/right, hides mapping.
Votes are stored in localStorage and exportable as CSV via the button.

Usage: python make_blind_html.py --manifest ..\\results\\metrics\\manifest.csv \
    --comparison t2t_vs_c2c --n 20
"""
import argparse
import base64
import csv
import html
import io
import json
import os
import random

from PIL import Image

PLAYGROUND = os.environ.get("PLAYGROUND", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def img_data_uri(path):
    img = Image.open(path).convert("RGB")
    img.thumbnail((768, 768))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--comparison", default="t2t_vs_c2c",
                    choices=["t2t_vs_c2c", "raw_vs_c2c", "raw_vs_t2t"])
    ap.add_argument("--pair", default=None, help="filter: pair key (e.g. pairA)")
    ap.add_argument("--backend", default=None, help="filter: backend (e.g. moss)")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    arm_a, arm_b = args.comparison.split("_vs_")
    rows = list(csv.DictReader(open(args.manifest, encoding="utf-8-sig")))
    by = {}
    for r in rows:
        if args.pair and r.get("pair") != args.pair:
            continue
        if args.backend and r.get("backend") != args.backend:
            continue
        if r["image_path"]:
            key = (r.get("pair", ""), r.get("backend", ""), r["prompt_id"], r["seed"])
            by.setdefault(key, {})[r["arm"]] = r

    cells = [k for k in by if arm_a in by[k] and arm_b in by[k]]
    rng = random.Random(args.seed)
    rng.shuffle(cells)
    cells = cells[: args.n]

    items = []
    for pair, backend, pid, seed in cells:
        ra, rb = by[(pair, backend, pid, seed)][arm_a], by[(pair, backend, pid, seed)][arm_b]
        flip = rng.random() < 0.5
        left, right = (rb, ra) if flip else (ra, rb)
        items.append({
            "id": f"{pid}_s{seed}",
            "prompt": ra["user_prompt"],
            "left": img_data_uri(left["image_path"]),
            "right": img_data_uri(right["image_path"]),
            "truth": {"left": left["arm"], "right": right["arm"]},
        })

    out = args.out or os.path.join(PLAYGROUND, "results", "blind",
                                   f"blind_{args.comparison}.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tpl = TEMPLATE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False))
    tpl = tpl.replace("__TITLE__", f"Blind eval: {args.comparison}")
    open(out, "w", encoding="utf-8").write(tpl)
    print(f"{len(items)} pairs -> {out}")


TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
body{font-family:system-ui;background:#111;color:#eee;margin:0;padding:24px}
.item{margin-bottom:40px;border-bottom:1px solid #333;padding-bottom:24px}
.prompt{font-size:15px;margin-bottom:12px;color:#9cf}
.row{display:flex;gap:16px}
.imgs{flex:1;display:flex;gap:12px}
.imgs img{width:48%;border:2px solid #444;border-radius:6px}
.q{margin:10px 0}
button{background:#246;color:#fff;border:0;border-radius:6px;padding:8px 14px;
margin:4px;font-size:14px;cursor:pointer}
button.sel{background:#2a2}
.bar{position:sticky;top:0;background:#111;padding:10px;z-index:9}
</style></head><body>
<div class="bar">
<b>__TITLE__</b> — 每对图回答两个问题（忠实度/观感），三选一。
<input id="who" placeholder="evaluator name (评估者署名)" style="padding:6px;border-radius:6px;border:1px solid #555;background:#222;color:#eee"> <button onclick="exportCSV()">导出 CSV</button>
<span id="prog"></span>
</div>
<div id="root"></div>
<script>
const ITEMS = __ITEMS__;
const votes = JSON.parse(localStorage.getItem('blind_votes_' + document.title) || '{}');
function render(){
  const root = document.getElementById('root');
  root.innerHTML = '';
  ITEMS.forEach((it, idx) => {
    const d = document.createElement('div'); d.className = 'item';
    const v = votes[it.id] || {};
    d.innerHTML = `
      <div class="prompt">#${idx+1} [${it.id}] ${it.prompt}</div>
      <div class="imgs"><img src="${it.left}"><img src="${it.right}"></div>
      <div class="q">Q1 忠实度（哪张更符合描述？）
        ${btn(it.id,'faith','left','左')}${btn(it.id,'faith','right','右')}${btn(it.id,'faith','tie','相当')}</div>
      <div class="q">Q2 观感（哪张更好看？）
        ${btn(it.id,'look','left','左')}${btn(it.id,'look','right','右')}${btn(it.id,'look','tie','相当')}</div>`;
    root.appendChild(d);
  });
  const done = Object.values(votes).filter(v=>v.faith&&v.look).length;
  document.getElementById('prog').textContent = ` 已完成 ${done}/${ITEMS.length}`;
}
function btn(id, q, val, label){
  const sel = (votes[id]||{})[q] === val ? 'sel' : '';
  return `<button class="${sel}" onclick="vote('${id}','${q}','${val}')">${label}</button>`;
}
function vote(id, q, val){
  votes[id] = votes[id] || {}; votes[id][q] = val;
  localStorage.setItem('blind_votes_' + document.title, JSON.stringify(votes)); render();
}
function exportCSV(){
  let csv = 'id,prompt,q,answer,truth_left,truth_right\\n';
  ITEMS.forEach(it=>{
    const v = votes[it.id] || {};
    ['faith','look'].forEach(q=>{
      if(v[q]) csv += `"${it.id}","${it.prompt.replace(/"/g,'""')}",${q},${v[q]},${it.truth.left},${it.truth.right}\\n`;
    });
  });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv'}));
  a.download = ('votes_' + (document.getElementById('who').value || 'anon') + '.csv').replace(/[^a-z0-9_.]/gi,'_');
  a.click();
}
render();
</script></body></html>
"""


if __name__ == "__main__":
    main()
