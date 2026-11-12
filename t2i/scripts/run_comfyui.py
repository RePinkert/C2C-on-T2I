"""Launch the local ComfyUI with the C2C node pack injected.

The user's ComfyUI installation directory is never written to: the pack is
exposed through a staging directory in runtime/ plus an extra-paths YAML
handed to ComfyUI via --extra-model-paths-config.

Usage
    python t2i/scripts/run_comfyui.py                 # start on :8188
    python t2i/scripts/run_comfyui.py --dry-run       # show the plan only
    python t2i/scripts/run_comfyui.py --port 8189
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paths  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8188)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--dry-run", action="store_true",
                    help="detect everything and print the command, do not start")
    ap.add_argument("--no-manager", action="store_true",
                    help="do not pass --enable-manager")
    ap.add_argument("--extra-arg", action="append", default=[],
                    help="extra argument forwarded to ComfyUI (repeatable)")
    args = ap.parse_args(argv)

    comfy_root, python_exe = paths.detect_comfyui()
    yaml_path = paths.write_comfy_extra_paths()

    cmd = [
        str(python_exe),
        str(comfy_root / "main.py"),
        "--port", str(args.port),
        "--listen", args.host,
        "--extra-model-paths-config", str(yaml_path),
    ]
    if not args.no_manager:
        cmd.append("--enable-manager")
    cmd.extend(args.extra_arg)

    print("ComfyUI root   :", comfy_root)
    print("interpreter    :", python_exe)
    print("node pack      :", paths.COMFY_PACK_DIR)
    print("staging link   :", paths.COMFY_NODES_STAGE_DIR / paths.COMFY_PACK_DIR.name)
    print("extra paths    :", yaml_path)
    print("command        :", " ".join(cmd))
    print("note           : the ComfyUI installation directory is not modified")

    if args.dry_run:
        return 0

    return subprocess.run(cmd, cwd=str(comfy_root)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
