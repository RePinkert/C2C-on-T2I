"""Autonomous batch runner: submits run files to ComfyUI and polls to completion.

Resumable: files already recorded as done in the log are skipped. Writes
results/batch_log.txt (one line per run). Run detached:

  venv\\Scripts\\python.exe workflows\\run_batch.py --files "workflows\\runs_v2\\A_moss_*.json"

or with an explicit list file (one path per line):
  venv\\Scripts\\python.exe workflows\\run_batch.py --list results\\batch_list.txt
"""
import argparse
import glob
import json
import os
import time
import urllib.request

BASE = "http://127.0.0.1:8188"
LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "batch_log.txt")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(path, payload=None):
    url = BASE + path
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def submit(wf_path):
    wf = json.load(open(wf_path, encoding="utf-8"))
    res = api("/prompt", {"prompt": wf, "client_id": "c2c-batch"})
    return res["prompt_id"]


def status(prompt_id):
    hist = api(f"/history/{prompt_id}")
    if prompt_id not in hist:
        return "running", []
    entry = hist[prompt_id]
    st = entry.get("status", {})
    if st.get("status_str") == "error":
        return "error", st.get("messages", [])[-3:]
    if entry.get("outputs"):
        return "completed", []
    return "running", []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", default=None, help="glob for workflow JSONs")
    ap.add_argument("--list", default=None, help="text file with one path per line")
    ap.add_argument("--timeout-min", type=int, default=15)
    args = ap.parse_args()

    if args.list:
        files = [l.strip().lstrip("\ufeff") for l in open(args.list, encoding="utf-8") if l.strip()]
    else:
        files = sorted(glob.glob(args.files))
    assert files, "no workflow files found"

    done = set()
    if os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8"):
            if " DONE " in line:
                done.add(line.split(" DONE ")[1].split(" (")[0].strip())

    todo = [f for f in files if os.path.basename(f) not in done]
    log(f"batch start: {len(todo)}/{len(files)} to run")
    for i, f in enumerate(todo):
        name = os.path.basename(f)
        try:
            pid = submit(f)
        except Exception as e:
            log(f"SUBMIT-FAIL {name}: {e}")
            continue
        log(f"SUBMIT {name} -> {pid}")
        t0 = time.time()
        while True:
            time.sleep(15)
            try:
                st, msgs = status(pid)
            except Exception:
                st = "running"
                msgs = []
            if st == "completed":
                log(f" DONE {name} ({(time.time()-t0)/60:.1f}min)")
                break
            if st == "error":
                log(f" ERROR {name}: {str(msgs)[:300]}")
                break
            if (time.time() - t0) / 60 > args.timeout_min:
                log(f" TIMEOUT {name}")
                try:
                    api("/interrupt", {})
                except Exception:
                    pass
                break
    log("batch finished")


if __name__ == "__main__":
    main()
