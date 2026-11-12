"""Rewrite absolute paths in tracked data files to their relative form.

    python t2i/eval/relocate_paths.py check       FILE...
    python t2i/eval/relocate_paths.py relativize  FILE...   # abs  -> rel
    python t2i/eval/relocate_paths.py absolutize   FILE...   # rel  -> abs

Options
    --base {t2i,project,runtime}   base for the relative form (default t2i)
    --dry-run                      print a preview, do not write
    --ext .csv,.json,.txt          restrict the files by suffix
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paths  # noqa: E402

ABS_PATH_RE = re.compile(r"(?<![\w'\"])[A-Z]:[\\/][^\s\"'<>|]*[\\/][^\s\"'<>|]*")


def _bases(name: str) -> Path:
    return {"t2i": paths.T2I_ROOT, "project": paths.PROJECT_ROOT,
            "runtime": paths.RUNTIME_ROOT}[name]


def relativize_text(text: str, base: Path) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        raw = m.group(0)
        trail = ""
        while raw and raw[-1] in ".,;:)]}":
            trail = raw[-1] + trail
            raw = raw[:-1]
        try:
            rel = Path(raw).resolve().relative_to(base.resolve()).as_posix()
        except (ValueError, OSError):
            return m.group(0)
        count += 1
        return rel + trail

    return ABS_PATH_RE.sub(repl, text), count


def absolutize_text(text: str, base: Path) -> tuple[str, int]:
    count = 0
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        if stripped and not Path(stripped).is_absolute() and ("/" in stripped or "\\" in stripped):
            cand = base / stripped.strip()
            if cand.exists():
                out.append(str(cand.resolve()) + line[len(stripped):])
                count += 1
                continue
        out.append(line)
    return "".join(out), count


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["check", "relativize", "absolutize"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--base", default="t2i", choices=["t2i", "project", "runtime"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ext", default="", help="comma separated suffixes, e.g. .csv,.txt")
    args = ap.parse_args(argv)

    base = _bases(args.base)
    suffixes = {s.strip() for s in args.ext.split(",") if s.strip()}

    total = 0
    for raw in args.files:
        path = Path(raw)
        if not path.is_absolute():
            path = paths.resolve(raw)
        if not path.exists():
            print("skip (missing): {}".format(path))
            continue
        if suffixes and path.suffix not in suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        if args.mode == "check":
            hits = ABS_PATH_RE.findall(text)
            if hits:
                print("{}: {} absolute path(s)".format(path, len(hits)))
                for h in sorted(set(hits))[:5]:
                    print("    {}".format(h))
            total += len(hits)
            continue
        if args.mode == "relativize":
            new_text, n = relativize_text(text, base)
        else:
            new_text, n = absolutize_text(text, base)
        total += n
        if n:
            print("{}: {} replacement(s)".format(path, n))
            if args.dry_run:
                for old, new in zip(text.splitlines(), new_text.splitlines()):
                    if old != new:
                        print("    - {}".format(old[:110]))
                        print("    + {}".format(new[:110]))
                        break
            else:
                path.write_text(new_text, encoding="utf-8")
    print("total replacements: {}".format(total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
