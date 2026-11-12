"""Validate the path hygiene of the C2C-on-T2I tree.

Four assertions (see t2i/docs/PATH_RESOLUTION.md §9):
  1. no drive-letter absolute paths in tracked text files
  2. every image_path in the metrics CSVs resolves
  3. every entry in batch_list.txt resolves
  4. the anchors satisfy invariant I1 and resolve/relative are inverse

Run:
    python t2i/eval/check_paths.py
    python t2i/eval/check_paths.py --json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paths  # noqa: E402

# A drive letter followed by at least one path separator. Requires two
# separators so that regex escapes such as "r'Answer:\s*(.*)'" are not
# mistaken for a Windows path.
ABS_PATH_RE = re.compile(r"(?<![\w'\"])[A-Z]:[\\/][^\s\"'<>|]*[\\/][^\s\"'<>|]*")

TEXT_SUFFIXES = {".py", ".json", ".csv", ".md", ".txt", ".yml", ".yaml", ".toml", ".html", ".sh", ".ps1"}

# Files that legitimately mention machine-specific installation paths.
ALLOWLIST = {
    "t2i/docs/HANDOFF.md",          # documents the local ComfyUI install path
    "t2i/docs/PATH_RESOLUTION.md",   # quotes them as examples
}


def tracked_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
        names = [n for n in out.split("\0") if n]
        return [root / n for n in names]
    except Exception:
        skip = {".git", "runtime", "exp_v2", "__pycache__", "node_modules"}
        return [p for p in root.rglob("*")
                if p.is_file() and not (set(p.relative_to(root).parts) & skip)]


def check_absolute_leaks(root: Path) -> list[dict]:
    findings = []
    for path in tracked_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in ALLOWLIST or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for m in ABS_PATH_RE.finditer(line):
                findings.append({"file": rel, "line": i, "match": m.group(0)})
    return findings


def check_metrics(resolve_base: Path) -> list[dict]:
    findings = []
    for name in ("manifest.csv", "image_metrics.csv"):
        csv_path = paths.METRICS_DIR / name
        if not csv_path.exists():
            findings.append({"file": name, "error": "missing"})
            continue
        with csv_path.open(encoding="utf-8-sig", newline="") as fh:
            for i, row in enumerate(csv.DictReader(fh), 2):
                rel = (row.get("image_path") or "").strip()
                if not rel:
                    continue
                target = resolve_base / rel
                if not target.exists():
                    findings.append({"file": name, "line": i, "image_path": rel,
                                     "error": "unresolvable"})
    return findings


def check_batch_list(resolve_base: Path) -> list[dict]:
    findings = []
    bl = paths.RESULTS_DIR / "batch_list.txt"
    if not bl.exists():
        return [{"file": "batch_list.txt", "error": "missing"}]
    for i, line in enumerate(bl.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        target = Path(line) if Path(line).is_absolute() else resolve_base / line
        if not target.exists():
            findings.append({"file": "batch_list.txt", "line": i, "entry": line,
                             "error": "unresolvable"})
    return findings


def check_anchors() -> list[dict]:
    findings = []
    if paths.RUNTIME_ROOT.parent != paths.PROJECT_ROOT:
        findings.append({"error": "I1 violated: RUNTIME_ROOT is not a child of PROJECT_ROOT",
                         "runtime": str(paths.RUNTIME_ROOT), "project": str(paths.PROJECT_ROOT)})
    sample = paths.T2I_ROOT / "exp_v2" / "_probe.png"
    if paths.resolve(paths.relative(sample)) != sample:
        findings.append({"error": "resolve/relative are not inverse"})
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--base", default="t2i", choices=["t2i", "project"],
                    help="base for resolving stored relative paths")
    args = ap.parse_args(argv)

    base = paths.T2I_ROOT if args.base == "t2i" else paths.PROJECT_ROOT
    report = {
        "absolute_path_leaks": check_absolute_leaks(paths.PROJECT_ROOT),
        "metrics_unresolvable": check_metrics(base),
        "batch_list_unresolvable": check_batch_list(base),
        "anchor_problems": check_anchors(),
    }
    total = sum(len(v) for v in report.values())
    report["total"] = total

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("path hygiene report  (base = {})".format(base))
        for key, items in report.items():
            if key == "total":
                continue
            print("\n{}: {}".format(key, len(items)))
            for it in items[:20]:
                print("   ", json.dumps(it, ensure_ascii=False))
            if len(items) > 20:
                print("    ... {} more".format(len(items) - 20))
        print("\ntotal problems: {}".format(total))
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
