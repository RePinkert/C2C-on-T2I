"""C2C bridge v2: T2T vs C2C prompt-enhancement generation for T2I experiments.

Runs inside the c2c venv. Loads receiver + sharer + pretrained C2C fuser once,
then generates prompts for one or many user ideas (batch mode amortizes load).

Changes vs v1 (research-grade fairness):
- unified token budget (256) for sharer analysis and final prompts
- --pair selects the fuser/model pair
- --batch-file runs N prompts in one process (steady-state latency)
- degeneration stats (rep-4gram / distinct-n) attached to every output
"""
import argparse
import contextlib
import json
import os
import re
import sys
import time

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "script", "playground"))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from inference_example import load_rosetta_model
from rosetta.utils.evaluate import set_default_chat_template

ROOT = os.path.dirname(os.path.abspath(__file__))

PAIRS = {
    "qwen3_0.6b+qwen2.5_0.5b": {
        "base_model": os.path.join(ROOT, "models", "Qwen3-0.6B"),
        "teacher_model": os.path.join(ROOT, "models", "Qwen2.5-0.5B-Instruct"),
        "checkpoints_dir": os.path.join(
            ROOT, "models", "c2c_fuser", "qwen3_0.6b+qwen2.5_0.5b_Fuser", "final"
        ),
    },
    "qwen3_0.6b+qwen3_4b_base": {
        "base_model": os.path.join(ROOT, "models", "Qwen3-0.6B"),
        "teacher_model": os.path.join(ROOT, "models", "Qwen3-4B-Base"),
        "checkpoints_dir": os.path.join(
            ROOT, "models", "c2c_fuser", "qwen3_0.6b+qwen3_4b_base_Fuser", "final"
        ),
    },
}

IMAGE_TASK_C2C = (
    "You are an expert prompt engineer for text-to-image models. "
    "Expand the user's idea into one detailed English image generation prompt: "
    "subject, action, setting, style, lighting, composition, quality tags. "
    "Output ONLY the final prompt text, nothing else.\n\n"
    "User idea: {idea}"
)
IMAGE_TASK_T2T_ANALYSIS = (
    "You are a visual concept analyst. For the image idea below, list the key visual "
    "elements: subject, style, composition, lighting, mood, notable details.\n\n"
    "Image idea: {idea}"
)
IMAGE_TASK_T2T_RECEIVER = (
    "You are an expert prompt engineer for text-to-image models. "
    "Expand the user's idea into one detailed English image generation prompt: "
    "subject, action, setting, style, lighting, composition, quality tags. "
    "Use the analysis below if helpful. Output ONLY the final prompt text, nothing else.\n\n"
    "User idea: {idea}\n\nAnalysis from assistant model:\n{analysis}"
)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def text_stats(text):
    tokens = re.findall(r"\S+", text.lower())
    n = max(len(tokens), 1)
    def distinct(k):
        grams = [tuple(tokens[i:i + k]) for i in range(len(tokens) - k + 1)]
        return round(len(set(grams)) / max(len(grams), 1), 4)
    grams4 = [tuple(tokens[i:i + 4]) for i in range(len(tokens) - 3)]
    rep4 = 0.0
    if grams4:
        from collections import Counter
        rep4 = max(Counter(grams4).values()) / len(grams4)
    degenerate = (distinct(2) < 0.35 and n > 20) or rep4 > 0.25
    return {
        "n_tokens": n,
        "distinct_1": distinct(1),
        "distinct_2": distinct(2),
        "distinct_3": distinct(3),
        "rep_4gram_max_ratio": round(rep4, 4),
        "degenerate": degenerate,
    }


def chat_text(model, tokenizer, user_content, max_new_tokens):
    messages = [{"role": "user", "content": user_content}]
    kwargs = {"tokenize": False, "add_generation_prompt": True}
    if "qwen3" in model.config._name_or_path.lower():
        kwargs["enable_thinking"] = False
    try:
        input_text = tokenizer.apply_chat_template(messages, **kwargs)
    except TypeError:
        kwargs.pop("enable_thinking", None)
        input_text = tokenizer.apply_chat_template(messages, **kwargs)
    inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
        )
    dt = time.time() - t0
    new_tokens = out[0, inputs["input_ids"].shape[1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip(), dt


def c2c_generate(rosetta_model, tokenizer, user_content, max_new_tokens):
    device = rosetta_model.device
    input_text = tokenizer.apply_chat_template(
        [{"role": "user", "content": user_content}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    inputs = tokenizer(input_text, return_tensors="pt").to(device)
    seq_len = inputs["input_ids"].shape[1]
    instruction_index = (
        torch.tensor([1, 0], dtype=torch.long).repeat(seq_len - 1, 1).unsqueeze(0).to(device)
    )
    label_index = torch.tensor([[-1, 0]], dtype=torch.long).unsqueeze(0).to(device)
    t0 = time.time()
    with torch.no_grad():
        out = rosetta_model.generate(
            **inputs,
            kv_cache_index=[instruction_index, label_index],
            do_sample=False,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
        )
    dt = time.time() - t0
    new_tokens = out[0, seq_len:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip(), dt


def run_one(rosetta_model, receiver, sharer, receiver_tok, sharer_tok, idea, mode, max_new_tokens):
    result = {"user_prompt": idea}
    if mode in ("both", "t2t"):
        analysis, a_s = chat_text(
            sharer, sharer_tok, IMAGE_TASK_T2T_ANALYSIS.format(idea=idea), max_new_tokens
        )
        t2t_text, r_s = chat_text(
            receiver, receiver_tok,
            IMAGE_TASK_T2T_RECEIVER.format(idea=idea, analysis=analysis),
            max_new_tokens,
        )
        result["t2t"] = {
            "text": t2t_text,
            "sharer_analysis": analysis,
            "analysis_seconds": round(a_s, 2),
            "receiver_seconds": round(r_s, 2),
            "total_seconds": round(a_s + r_s, 2),
            "text_stats": text_stats(t2t_text),
        }
    if mode in ("both", "c2c"):
        c2c_text, c_s = c2c_generate(
            rosetta_model, receiver_tok, IMAGE_TASK_C2C.format(idea=idea), max_new_tokens
        )
        result["c2c"] = {
            "text": c2c_text,
            "total_seconds": round(c_s, 2),
            "text_stats": text_stats(c2c_text),
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-prompt", default=None)
    parser.add_argument("--batch-file", default=None,
                        help='JSON list of {"id": ..., "prompt": ...} or plain strings')
    parser.add_argument("--pair", default="qwen3_0.6b+qwen2.5_0.5b", choices=list(PAIRS))
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--mode", choices=["both", "t2t", "c2c"], default="both")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if not args.user_prompt and not args.batch_file:
        parser.error("need --user-prompt or --batch-file")

    if args.batch_file:
        with open(args.batch_file, "r", encoding="utf-8") as f:
            items = json.load(f)
        ideas = [
            (it.get("id", f"item{i}"), it["prompt"]) if isinstance(it, dict) else (f"item{i}", it)
            for i, it in enumerate(items)
        ]
    else:
        ideas = [("item0", args.user_prompt)]

    cfg = PAIRS[args.pair]
    real_stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        t0 = time.time()
        rosetta_model, receiver_tok = load_rosetta_model(
            model_config={"rosetta_config": cfg}, eval_config={}, device=torch.device("cuda")
        )
        load_s = time.time() - t0
        receiver = rosetta_model.model_list[0]
        sharer = rosetta_model.model_list[1]
        sharer_tok = AutoTokenizer.from_pretrained(cfg["teacher_model"])
        set_default_chat_template(sharer_tok, cfg["teacher_model"])

    results = {
        "pair": args.pair,
        "max_new_tokens": args.max_new_tokens,
        "load_seconds": round(load_s, 2),
        "device": torch.cuda.get_device_name(0),
        "items": [],
    }
    for item_id, idea in ideas:
        t0 = time.time()
        r = run_one(rosetta_model, receiver, sharer, receiver_tok, sharer_tok,
                    idea, args.mode, args.max_new_tokens)
        r["id"] = item_id
        r["wall_seconds"] = round(time.time() - t0, 2)
        results["items"].append(r)
        log(f"[{item_id}] done in {r['wall_seconds']}s")

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with real_stdout:
        print(json.dumps({"ok": True, "out": args.out, "n": len(results["items"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
