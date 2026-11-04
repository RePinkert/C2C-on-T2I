"""Smoke test: official C2C pretrained fuser (qwen3_0.6b+qwen2.5_0.5b) on local GPU."""
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "script", "playground"))

import torch
from inference_example import load_rosetta_model

ROOT = os.path.dirname(os.path.abspath(__file__))

model_config = {
    "rosetta_config": {
        "base_model": os.path.join(ROOT, "models", "Qwen3-0.6B"),
        "teacher_model": os.path.join(ROOT, "models", "Qwen2.5-0.5B-Instruct"),
        "checkpoints_dir": os.path.join(
            ROOT, "models", "c2c_fuser", "qwen3_0.6b+qwen2.5_0.5b_Fuser", "final"
        ),
    }
}

t0 = time.time()
rosetta_model, tokenizer = load_rosetta_model(model_config, eval_config={}, device=torch.device("cuda"))
print(f"model loaded in {time.time()-t0:.1f}s")

prompt = [{"role": "user", "content": "Say hello in one short sentence."}]
input_text = tokenizer.apply_chat_template(
    prompt, tokenize=False, add_generation_prompt=True, enable_thinking=False
)
inputs = tokenizer(input_text, return_tensors="pt").to(rosetta_model.device)

instruction_index = (
    torch.tensor([1, 0], dtype=torch.long)
    .repeat(inputs["input_ids"].shape[1] - 1, 1)
    .unsqueeze(0)
    .to(rosetta_model.device)
)
label_index = torch.tensor([[-1, 0]], dtype=torch.long).unsqueeze(0).to(rosetta_model.device)
kv_cache_index = [instruction_index, label_index]

with torch.no_grad():
    t0 = time.time()
    outputs = rosetta_model.generate(
        **inputs,
        kv_cache_index=kv_cache_index,
        do_sample=False,
        max_new_tokens=64,
    )
    dt = time.time() - t0
new_tokens = outputs[0, instruction_index.shape[1] + 1 :]
print(f"C2C output: {tokenizer.decode(new_tokens, skip_special_tokens=True)!r}")
print(f"generate time: {dt:.2f}s, new tokens: {new_tokens.shape[0]}")
print("SMOKE OK")
