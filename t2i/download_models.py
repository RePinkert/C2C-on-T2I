import os
import sys

import huggingface_hub

TARGETS = [
    ("nics-efc/C2C_Fuser", ["qwen3_0.6b+qwen2.5_0.5b_Fuser/*"], "models/c2c_fuser"),
    ("nics-efc/C2C_Fuser", ["qwen3_0.6b+qwen3_4b_base_Fuser/*"], "models/c2c_fuser"),
    ("Qwen/Qwen3-0.6B", None, "models/Qwen3-0.6B"),
    ("Qwen/Qwen2.5-0.5B-Instruct", None, "models/Qwen2.5-0.5B-Instruct"),
    ("Qwen/Qwen3-4B-Base", None, "models/Qwen3-4B-Base"),
]


def download(endpoint=None):
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint
        huggingface_hub.constants.ENDPOINT = endpoint
    for repo_id, patterns, local in TARGETS:
        print(f"== {repo_id} -> {local} (endpoint={os.environ.get('HF_ENDPOINT')})")
        huggingface_hub.snapshot_download(
            repo_id=repo_id,
            allow_patterns=patterns,
            local_dir=local,
        )
        print(f"   done: {local}")


if __name__ == "__main__":
    try:
        download()
    except Exception as e:
        print(f"direct failed: {type(e).__name__}: {e}", file=sys.stderr)
        download("https://hf-mirror.com")
