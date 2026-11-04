"""ComfyUI-C2C: Cache-to-Cache prompt enhancement nodes (T2T vs C2C comparison)."""
import json
import os
import subprocess
import tempfile
import time

# Point C2C_ROOT at the directory containing c2c_bridge.py (this repo's t2i/).
# VENV_PY must be a Python with the C2C deps installed (see t2i/docs/REPRODUCE.md).
C2C_ROOT = os.environ.get(
    "C2C_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
BRIDGE_PY = os.path.join(C2C_ROOT, "c2c_bridge.py")
VENV_PY = os.path.join(C2C_ROOT, "venv", "Scripts", "python.exe")

PAIRS = ["qwen3_0.6b+qwen2.5_0.5b", "qwen3_0.6b+qwen3_4b_base"]


class C2CCompare:
    """Generate image prompts via T2T relay and via C2C KV-cache fusion in one subprocess."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "user_prompt": ("STRING", {"multiline": True, "default": "a red fox in the snow"}),
                "max_new_tokens": ("INT", {"default": 256, "min": 16, "max": 512}),
            },
            "optional": {
                "mode": (["both", "t2t", "c2c"], {"default": "both"}),
                "pair": (PAIRS, {"default": PAIRS[0]}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("t2t_prompt", "c2c_prompt", "meta_json")
    FUNCTION = "compare"
    CATEGORY = "C2C"

    def compare(self, user_prompt, max_new_tokens, mode="both", pair=PAIRS[0]):
        if not os.path.exists(VENV_PY):
            raise RuntimeError(f"C2C venv python not found: {VENV_PY}")
        if not os.path.exists(BRIDGE_PY):
            raise RuntimeError(f"c2c_bridge.py not found: {BRIDGE_PY}")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tf:
            out_path = tf.name
        try:
            proc = subprocess.run(
                [
                    VENV_PY, BRIDGE_PY,
                    "--user-prompt", user_prompt,
                    "--max-new-tokens", str(max_new_tokens),
                    "--mode", mode,
                    "--pair", pair,
                    "--out", out_path,
                ],
                capture_output=True,
                text=True,
                timeout=900,
                cwd=C2C_ROOT,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"c2c_bridge failed (rc={proc.returncode}):\n{proc.stderr[-3000:]}"
                )
            with open(out_path, "r", encoding="utf-8") as f:
                result = json.load(f)
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)

        item = result.get("items", [{}])[0]
        t2t = item.get("t2t", {})
        c2c = item.get("c2c", {})
        meta = {
            "pair": result.get("pair"),
            "load_seconds": result.get("load_seconds"),
            "device": result.get("device"),
            "t2t_seconds": t2t.get("total_seconds"),
            "c2c_seconds": c2c.get("total_seconds"),
            "t2t_text_stats": t2t.get("text_stats"),
            "c2c_text_stats": c2c.get("text_stats"),
            "sharer_analysis": t2t.get("sharer_analysis", ""),
            "user_prompt": user_prompt,
            "t2t_prompt": t2t.get("text", ""),
            "c2c_prompt": c2c.get("text", ""),
        }
        meta_dir = os.path.join(C2C_ROOT, "..", "results", "meta")
        try:
            os.makedirs(meta_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            with open(os.path.join(meta_dir, f"c2c_meta_{stamp}.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
        return (t2t.get("text", ""), c2c.get("text", ""), json.dumps(meta, ensure_ascii=False))


NODE_CLASS_MAPPINGS = {
    "C2CCompare": C2CCompare,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "C2CCompare": "C2C Compare (T2T vs Cache-to-Cache)",
}
