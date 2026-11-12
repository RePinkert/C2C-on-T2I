"""Canonical path resolution for the C2C-on-T2I toolchain.

Anchors
    PROJECT_ROOT   repository root (holds pyproject.toml + t2i/)
    T2I_ROOT       t2i/       -- toolchain and artifacts (tracked by git)
    RUNTIME_ROOT   runtime/   -- weights + python env (git-ignored)

Invariant I1
    RUNTIME_ROOT is a direct child of PROJECT_ROOT, therefore
        PROJECT_ROOT = dirname(RUNTIME_ROOT)
        T2I_ROOT     = PROJECT_ROOT / "t2i"
    Knowing the runtime location is enough to derive the other two.

Detection order for PROJECT_ROOT
    1. C2C_PROJECT_ROOT environment variable
    2. walk up from Path(__file__).resolve() looking for pyproject.toml + t2i/
    3. walk up from Path.cwd().resolve() with the same rule
    4. otherwise raise, with actionable repair instructions

Path(__file__).resolve() is deliberate: it resolves symlinks and Windows
junctions (os.path.realpath), so a node pack loaded through
custom_nodes/ComfyUI-C2C -> <repo>/t2i/ComfyUI-C2C still finds the repo.
"""
from __future__ import annotations

import os
import subprocess
import sys
import warnings
from pathlib import Path

__all__ = [
    "PROJECT_ROOT", "T2I_ROOT", "RUNTIME_ROOT",
    "RESULTS_DIR", "METRICS_DIR", "BLIND_DIR", "FIGS_DIR", "EXP_OUT",
    "DOCS_DIR", "WORKFLOWS_DIR", "PROMPTS_FILE", "COMFY_PACK_DIR",
    "MODELS_DIR", "VENV_PY", "BRIDGE_PY",
    "COMFY_NODES_STAGE_DIR", "COMFY_EXTRA_PATHS_YAML",
    "resolve", "relative", "require_runtime",
    "detect_comfyui", "write_comfy_extra_paths",
]


# --------------------------------------------------------------------------
# anchors
# --------------------------------------------------------------------------
def _is_project_root(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "t2i").is_dir()


def _find_project_root(start: Path) -> Path | None:
    for cand in [start, *start.parents]:
        if _is_project_root(cand):
            return cand
    return None


def _detect_project_root() -> Path:
    env = os.environ.get("C2C_PROJECT_ROOT")
    if env:
        cand = Path(env).expanduser().resolve()
        if _is_project_root(cand):
            return cand
        raise RuntimeError(
            "C2C_PROJECT_ROOT={!r} is not a C2C-on-T2I project root "
            "(expected pyproject.toml and t2i/ inside it)".format(env)
        )

    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        found = _find_project_root(start)
        if found is not None:
            return found

    raise RuntimeError(
        "Cannot locate the C2C-on-T2I project root.\n"
        "Fix it by any of:\n"
        "  - set C2C_PROJECT_ROOT to the repository root\n"
        "  - run the script from inside the repository\n"
        "  - keep t2i/paths.py under a directory that also holds pyproject.toml"
    )


PROJECT_ROOT: Path = _detect_project_root()
T2I_ROOT: Path = PROJECT_ROOT / "t2i"

# I1: runtime/ is a direct child of the project root.
_runtime_env = os.environ.get("C2C_RUNTIME") or os.environ.get("C2C_ROOT")
RUNTIME_ROOT: Path = (
    Path(_runtime_env).expanduser().resolve() if _runtime_env else PROJECT_ROOT / "runtime"
)

RESULTS_DIR: Path = T2I_ROOT / "results"
METRICS_DIR: Path = RESULTS_DIR / "metrics"
BLIND_DIR: Path = RESULTS_DIR / "blind"
FIGS_DIR: Path = T2I_ROOT / "report" / "figures"
EXP_OUT: Path = T2I_ROOT / "exp_v2"
DOCS_DIR: Path = T2I_ROOT / "docs"
WORKFLOWS_DIR: Path = T2I_ROOT / "workflows"
PROMPTS_FILE: Path = T2I_ROOT / "prompts_v2.json"
COMFY_PACK_DIR: Path = T2I_ROOT / "ComfyUI-C2C"

MODELS_DIR: Path = RUNTIME_ROOT / "models"
VENV_PY: Path = RUNTIME_ROOT / "venv" / "Scripts" / "python.exe"
BRIDGE_PY: Path = RUNTIME_ROOT / "c2c_bridge.py"

# Staging area used to inject the node pack into ComfyUI without touching
# the user's ComfyUI installation directory.
COMFY_NODES_STAGE_DIR: Path = RUNTIME_ROOT / "comfy_nodes"
COMFY_EXTRA_PATHS_YAML: Path = RUNTIME_ROOT / "comfy_extra_paths.yaml"


# --------------------------------------------------------------------------
# conversions
# --------------------------------------------------------------------------
def resolve(p, base: Path = T2I_ROOT) -> Path:
    """Absolute path -> Path. Relative inputs resolve against 'base'."""
    p = Path(p)
    return p if p.is_absolute() else (base / p)


def relative(p, base: Path = T2I_ROOT) -> str:
    """Absolute path -> POSIX-style path relative to 'base' (storage form)."""
    return Path(p).resolve().relative_to(base.resolve()).as_posix()


def require_runtime() -> None:
    """Fail with actionable steps when the runtime assets are absent (G4)."""
    missing = [d for d in (MODELS_DIR, VENV_PY.parent) if not d.exists()]
    if missing:
        raise RuntimeError(
            "Runtime assets are missing under {}\n".format(RUNTIME_ROOT)
            + "Populate it with:\n"
            + "  python t2i/download_models.py\n"
            + "  uv venv runtime/venv --python 3.10\n"
            + "  uv pip install --python runtime/venv/Scripts/python.exe <deps>"
        )


# --------------------------------------------------------------------------
# ComfyUI discovery + node-pack injection
# --------------------------------------------------------------------------
def _comfyui_candidates() -> list[Path]:
    cands: list[Path] = []
    for var in ("COMFYUI_HOME", "COMFYUI_PATH", "COMFYUI_ROOT"):
        v = os.environ.get(var)
        if v:
            cands.append(Path(v).expanduser())

    # comfy-cli's own config records the workspace it manages
    cfg = Path.home() / "AppData" / "Local" / "comfy-cli" / "config.ini"
    if cfg.exists():
        try:
            import configparser

            cp = configparser.ConfigParser()
            cp.read(cfg, encoding="utf-8")
            for key in ("default_workspace", "recent_workspace"):
                val = cp.get("comfy-cli", key, fallback=None) or cp.get("default", key, fallback=None)
                if val:
                    cands.append(Path(val))
        except Exception:
            pass

    home = Path.home()
    cands += [
        Path("C:/ComfyUI"),
        home / "ComfyUI",
        home / "Documents" / "ComfyUI",
        Path("C:/cc/ComfyUI_windows_portable/ComfyUI"),
        Path("D:/ComfyUI"),
        Path("D:/cc/ComfyUI_windows_portable/ComfyUI"),
    ]
    return cands


def detect_comfyui() -> tuple[Path, Path]:
    """Locate the local ComfyUI installation and its interpreter.

    Returns (comfy_root, python_exe). Raises RuntimeError with the list of
    probed locations when nothing is found.
    """
    probed = []
    for cand in _comfyui_candidates():
        try:
            cand = cand.expanduser()
        except Exception:
            continue
        if not cand.exists():
            probed.append(str(cand))
            continue
        # the workspace itself, or its parent when given the launcher dir
        for root in (cand, cand.parent if cand.name.lower() == "comfyui" else cand):
            if (root / "main.py").exists() and (root / "nodes.py").exists():
                py = None
                for rel in ("../python_embeded/python.exe", "python_embeded/python.exe",
                            "../python/python.exe", "python.exe"):
                    cand_py = (root / rel).resolve()
                    if cand_py.exists():
                        py = cand_py
                        break
                if py is None:
                    py = Path(sys.executable)
                return root.resolve(), py
        probed.append(str(cand))

    raise RuntimeError(
        "Cannot locate a local ComfyUI installation.\n"
        "Set COMFYUI_HOME to the ComfyUI directory, then retry.\n"
        "Probed: " + ", ".join(probed)
    )


def write_comfy_extra_paths() -> Path:
    """Stage the node pack and emit the extra-paths YAML for ComfyUI.

    The pack is exposed to ComfyUI through a staging directory that holds a
    single entry (a link to the in-repo pack). ComfyUI is then started with
    --extra-model-paths-config <yaml>, so the user's ComfyUI directory is
    never written to.
    """
    COMFY_NODES_STAGE_DIR.mkdir(parents=True, exist_ok=True)
    staged = COMFY_NODES_STAGE_DIR / COMFY_PACK_DIR.name
    if staged.exists() or staged.is_symlink():
        # a junction must be removed with rmdir, never with -Recurse
        subprocess.run(["cmd", "/c", "rmdir", str(staged)], check=False,
                       capture_output=True)
    # directory junction: no admin rights needed, unlike a symlink
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(staged), str(COMFY_PACK_DIR)],
        check=True, capture_output=True, text=True,
    )

    yaml_text = (
        "# Generated by C2C-on-T2I -- do not edit, regenerated on every launch.\n"
        "# Points ComfyUI at the in-repo node pack WITHOUT modifying the\n"
        "# user's ComfyUI installation directory.\n"
        "c2c_on_t2i:\n"
        "    custom_nodes: {}\n".format(COMFY_NODES_STAGE_DIR.as_posix())
    )
    COMFY_EXTRA_PATHS_YAML.write_text(yaml_text, encoding="utf-8")
    return COMFY_EXTRA_PATHS_YAML


def _deprecation(old: str, new: str) -> None:
    warnings.warn(
        "{} is deprecated, use {}".format(old, new),
        DeprecationWarning,
        stacklevel=3,
    )


def _legacy_env(name: str, new: str) -> str | None:
    value = os.environ.get(new)
    if value:
        return value
    value = os.environ.get(name)
    if value:
        _deprecation(name, new)
    return value
