"""Generate a blind-eval HTML page from the manifest.

Pairs arms per (prompt_id, seed), randomizes left/right, hides mapping.
Votes are stored in localStorage and exportable as CSV via the button.

Two modes:
  single comparison:
    python make_blind_html.py --comparison t2t_vs_c2c --n 20
  mixed (3 comparisons, unique prompts, interleaved order):
    python make_blind_html.py --mixed 7,7,7
    -> blind_compare_all.html with 21 pairs over 21 unique prompts:
       7x raw_vs_c2c + 7x raw_vs_t2t + 7x t2t_vs_c2c
"""
import argparse
import base64
import csv
import io
import json
import os
import random

from PIL import Image

PLAYGROUND = r"C:\Yet\Playground"
MIXED_COMPARISONS = ["raw_vs_c2c", "raw_vs_t2t", "t2t_vs_c2c"]
SEEDS = ["42", "1042", "2042"]


def img_data_uri(path):
    img = Image.open(path).convert("RGB")
    img.thumbnail((768, 768))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def load_rows(manifest, pair, backend):
    rows = list(csv.DictReader(open(manifest, encoding="utf-8-sig")))
    by = {}
    for r in rows:
        if pair and r.get("pair") != pair:
            continue
        if backend and r.get("backend") != backend:
            continue
        if r["image_path"]:
            key = (r.get("pair", ""), r.get("backend", ""), r["prompt_id"], r["seed"])
            by.setdefault(key, {})[r["arm"]] = r
    return by


def cell_item(by, pair, backend, pid, seed, arm_a, arm_b, flip_rng):
    ra, rb = by[(pair, backend, pid, seed)][arm_a], by[(pair, backend, pid, seed)][arm_b]
    flip = flip_rng.random() < 0.5
    left, right = (rb, ra) if flip else (ra, rb)
    return {
        "id": f"{pid}_s{seed}",
        "prompt": ra["user_prompt"],
        "left": img_data_uri(left["image_path"]),
        "right": img_data_uri(right["image_path"]),
        "truth": {"left": left["arm"], "right": right["arm"]},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--comparison", default="t2t_vs_c2c",
                    choices=["t2t_vs_c2c", "raw_vs_c2c", "raw_vs_t2t"])
    ap.add_argument("--mixed", default=None, metavar="N1,N2,N3",
                    help="per-comparison counts for raw_vs_c2c,raw_vs_t2t,t2t_vs_c2c, e.g. 7,7,7")
    ap.add_argument("--pair", default=None, help="filter: pair key (e.g. pairA)")
    ap.add_argument("--backend", default=None, help="filter: backend (e.g. moss)")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.mixed:
        if not args.pair:
            args.pair = "qwen3_0.6b+qwen2.5_0.5b"
            print(f"mixed mode: defaulting --pair to {args.pair}")
        if not args.backend:
            args.backend = "moss"
            print(f"mixed mode: defaulting --backend to {args.backend}")
    by = load_rows(args.manifest, args.pair, args.backend)
    rng = random.Random(args.seed)

    if args.mixed:
        counts = [int(x) for x in args.mixed.split(",")]
        assert len(counts) == 3, "--mixed takes 3 counts: raw_vs_c2c,raw_vs_t2t,t2t_vs_c2c"
        pids_all = sorted({k[2] for k in by})
        rng.shuffle(pids_all)
        groups = {c: [] for c in MIXED_COMPARISONS}
        i = 0
        while any(len(groups[c]) < counts[j] for j, c in enumerate(MIXED_COMPARISONS)):
            for j, c in enumerate(MIXED_COMPARISONS):
                if len(groups[c]) < counts[j]:
                    groups[c].append(pids_all[i])
                    i += 1
        # language balance fix: each group prefers >= 2 zh prompts
        lang = {}
        for k, arms in by.items():
            if "user_prompt" in arms.get("raw", {}):
                lang[k[2]] = "zh" if any('一' <= ch <= '鿿' for ch in arms["raw"]["user_prompt"]) else "en"
        for j, c in enumerate(MIXED_COMPARISONS):
            need = 2 - sum(1 for p in groups[c] if lang.get(p) == "zh")
            if need <= 0:
                continue
            for other in MIXED_COMPARISONS:
                if other == c:
                    continue
                for p in list(groups[other]):
                    if lang.get(p) == "zh" and sum(1 for q in groups[other] if lang.get(q) == "zh") > 2:
                        groups[c].append(p)
                        groups[other].remove(p)
                        need -= 1
                        if need == 0:
                            break
                if need == 0:
                    break
        bundles = []
        for j, c in enumerate(MIXED_COMPARISONS):
            for p in groups[c]:
                bundles.append({"pid": p, "pair_type": c})
        rng.shuffle(bundles)
        items = []
        for k, b in enumerate(bundles):
            seed = SEEDS[k % 3]
            arm_a, arm_b = b["pair_type"].split("_vs_")
            items.append(cell_item(by, args.pair, args.backend,
                                   b["pid"], seed, arm_a, arm_b, rng))
        rng.shuffle(items)
        rng.shuffle(items)
        title = "盲评：raw / t2t / c2c"
        out_name = "blind_compare_all.html"
        print("group assignment:")
        for c in MIXED_COMPARISONS:
            print(f"  {c}: {groups[c]}")
    else:
        arm_a, arm_b = args.comparison.split("_vs_")
        cells = [k for k in by if arm_a in by[k] and arm_b in by[k]]
        rng.shuffle(cells)
        cells = cells[: args.n]
        items = []
        for pair, backend, pid, seed in cells:
            items.append(cell_item(by, pair, backend, pid, seed, arm_a, arm_b, rng))
        title = f"Blind eval: {args.comparison}"
        out_name = f"blind_{args.comparison}.html"

    out = args.out or os.path.join(PLAYGROUND, "results", "blind", out_name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tpl = TEMPLATE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False))
    tpl = tpl.replace("__TITLE__", title)
    open(out, "w", encoding="utf-8").write(tpl)
    print(f"{len(items)} pairs -> {out}")


TEMPLATE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#12151a;--card:#1b2028;--txt:#e8ecf3;--dim:#8b95a7;--acc:#3b82f6;--ok:#22c55e;--warn:#f59e0b}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--txt);padding:0}
.top{position:sticky;top:0;z-index:20;background:rgba(18,21,26,.96);backdrop-filter:blur(8px);
  border-bottom:1px solid #242b36;padding:12px 16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.top b{font-size:15px;margin-right:auto}
.hint{color:var(--dim);font-size:12px;width:100%;margin-top:-2px}
#who{padding:7px 10px;border-radius:8px;border:1px solid #2c3442;background:#151a21;color:var(--txt);font-size:13px;width:170px}
.btn{background:#21304a;border:0;color:#cfe0ff;border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer}
.btn:hover{background:#2a3f5f}
.btn.warn{background:#3d2a1a;color:#ffd9a0}
.bar{height:5px;background:#222a35;border-radius:3px;overflow:hidden;margin:10px 16px 0}
.bar>div{height:100%;background:var(--acc);width:0%;transition:width .25s}
#resume{display:none;margin:12px 16px 0;padding:10px 14px;border:1px solid #54431e;background:#2a2110;
  border-radius:10px;color:#ffd98a;font-size:13px}
#resume button{margin-left:8px}
#root{max-width:1080px;margin:0 auto;padding:16px}
.item{background:var(--card);border:1px solid #242b36;border-radius:14px;padding:16px 18px;margin-bottom:18px}
.meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:12px}
.meta .idx{color:var(--dim);font-size:12px;white-space:nowrap}
.prompt{font-size:15px;line-height:1.6;color:#bcd3ff;word-break:break-word}
.imgs{display:flex;gap:12px;margin:12px 0}
.imgs figure{flex:1;text-align:center}
.imgs img{width:100%;max-height:56vh;object-fit:contain;border:2px solid #2c3442;border-radius:10px;background:#0c0f14}
.imgs figcaption{color:var(--dim);font-size:12px;margin-top:6px}
.q{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:8px}
.q .qt{min-width:150px;font-size:13px;color:var(--dim)}
.opt{background:#222b38;border:1px solid #2c3442;color:var(--txt);border-radius:8px;
  padding:8px 16px;font-size:14px;cursor:pointer;min-width:88px}
.opt:hover{border-color:#3b82f6}
.opt.sel{background:var(--ok);border-color:var(--ok);color:#052e12;font-weight:700}
.done{color:var(--ok);font-size:13px;margin-left:8px}
@media (max-width:760px){
  .imgs{flex-direction:column}
  .imgs img{max-height:38vh}
  .q .qt{min-width:100%;margin-bottom:4px}
  #who{width:100%}
}
</style></head><body>
<div class="top">
  <b>__TITLE__</b>
  <input id="who" placeholder="昵称（仅用于区分问卷）">
  <button class="btn" onclick="exportCSV()">导出 CSV</button>
  <button class="btn warn" onclick="resetVotes()">清除本地进度</button>
  <span id="prog"></span>
  <div class="hint">每对图回答两个问题（忠实度 / 观感），三选一。左右顺序已随机化。所有数据仅存于你的浏览器本地。</div>
</div>
<div class="bar"><div id="barfill"></div></div>
<div id="resume">检测到本地已有 <b id="resumeN"></b>/21 对作答。
  <button class="btn" onclick="dismissResume()">继续作答</button>
  <button class="btn warn" onclick="resetVotes()">清除重来</button>
</div>
<div id="root"></div>
<script>
const ITEMS = __ITEMS__;
const KEY = 'blind_votes_v2_compare_all';
let votes = {};
try { votes = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch(e) { votes = {}; }
const root = document.getElementById('root');
ITEMS.forEach((it, idx) => {
  const d = document.createElement('div');
  d.className = 'item';
  d.innerHTML = `
    <div class="meta"><span class="prompt">#${idx+1} ${escapeHtml(it.prompt)}</span>
      <span class="idx">${idx+1}/21</span></div>
    <div class="imgs">
      <figure><img src="${it.left}" alt="left"><figcaption>左图</figcaption></figure>
      <figure><img src="${it.right}" alt="right"><figcaption>右图</figcaption></figure>
    </div>
    <div class="q"><span class="qt">Q1 忠实度：哪张更符合文字描述？</span>
      ${opt(it.id,'faith','left','← 左图')}${opt(it.id,'faith','tie','相当')}${opt(it.id,'faith','right','右图 →')}
      <span class="done" data-d="${it.id}:faith"></span></div>
    <div class="q"><span class="qt">Q2 观感：哪张更好看？</span>
      ${opt(it.id,'look','left','← 左图')}${opt(it.id,'look','tie','相当')}${opt(it.id,'look','right','右图 →')}
      <span class="done" data-d="${it.id}:look"></span></div>`;
  root.appendChild(d);
});
function escapeHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');}
function opt(id,q,val,label){
  const sel = (votes[id]||{})[q]===val ? ' sel' : '';
  return `<button class="opt${sel}" onclick="vote('${id}','${q}','${val}')">${label}</button>`;
}
function vote(id,q,val){
  votes[id] = votes[id] || {}; votes[id][q] = val;
  localStorage.setItem(KEY, JSON.stringify(votes));
  refresh();
}
function doneCount(){ return ITEMS.filter(it => (votes[it.id]||{}).faith && (votes[it.id]||{}).look).length; }
function refresh(){
  root.querySelectorAll('.opt').forEach(b => b.classList.remove('sel'));
  root.querySelectorAll('.done').forEach(s => s.textContent='');
  ITEMS.forEach(it => {
    const v = votes[it.id] || {};
    for (const q of ['faith','look']) {
      if (v[q]) {
        const el = root.querySelector(`[onclick="vote('${it.id}','${q}','${v[q]}')"]`);
        if (el) el.classList.add('sel');
        const done = root.querySelector(`[data-d="${it.id}:${q}"]`);
        if (done) done.textContent = '✓';
      }
    }
  });
  const n = doneCount();
  document.getElementById('prog').textContent = n === ITEMS.length ? `已完成 ${n}/${ITEMS.length}，可以导出了 ✓` : `已完成 ${n}/${ITEMS.length}`;
  document.getElementById('barfill').style.width = (100*n/ITEMS.length)+'%';
  document.getElementById('resume').style.display = 'none';
}
function resetVotes(){
  if (!confirm('清除本地所有作答并重新开始？')) return;
  votes = {}; localStorage.removeItem(KEY); refresh();
}
function dismissResume(){ document.getElementById('resume').style.display='none'; }
function exportCSV(){
  let csv = 'id,prompt,q,answer,truth_left,truth_right\\n';
  ITEMS.forEach(it => {
    const v = votes[it.id] || {};
    ['faith','look'].forEach(q => {
      if (v[q]) csv += `"${it.id}","${String(it.prompt).replace(/"/g,'""')}",${q},${v[q]},${it.truth.left},${it.truth.right}\\n`;
    });
  });
  const who = (document.getElementById('who').value || 'anon').replace(/[\\/:*?"<>|]/g,'_');
  const ts = new Date().toISOString().slice(0,19).replace(/[-:T]/g,'');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
  a.download = `votes_${who}_${ts}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}
const saved = doneCount();
if (saved > 0) {
  document.getElementById('resume').style.display = 'block';
  document.getElementById('resumeN').textContent = saved;
}
refresh();
</script></body></html>
"""

if __name__ == "__main__":
    main()
