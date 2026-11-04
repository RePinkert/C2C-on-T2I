"""Build API-format ComfyUI workflows for the C2C vs T2T vs RAW experiment (v2).

One workflow = one (prompt, seed) cell, THREE arms (raw / t2t / c2c) sharing the
same noise. Outputs: 3 unlabeled singles (blind eval) + 1 labeled 3-way concat.

Two modes:
- embedded (batch experiments): t2t/c2c prompt TEXTS are literals from a
  pre-generated texts file (bridge --batch-file output). No LLM runs at image
  time -> fast, deterministic, reproducible stimuli.
- --live (interactive/pilot): a C2CCompare node generates texts at runtime.

Usage:
  # batch: after running c2c_bridge --batch-file for each pair
  python build_workflow.py --matrix --backend moss \
      --texts ..\\results\\prompts_generated\\pairA.json --seeds 42,1042,2042
  # live pilot
  python build_workflow.py --live --backend krea2 --prompt "..." --seed 42 --tag pilot
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "runs_v2")
PROMPTS_FILE = os.path.join(os.path.dirname(HERE), "prompts_v2.json")
TEXTS_DIR = os.path.join(os.path.dirname(HERE), "results", "prompts_generated")

BACKENDS = {
    "moss": {
        "unet": "moodyMossMixFreeDownload_v1025STEPSCFG3_fp8.safetensors",
        "clip": "qwen3.5_9b_uncensored_int8_convrot.safetensors",
        "clip_type": "moss_image",
        "clip_device": "cpu",
        "vae": "flux2-vae.safetensors",
        "latent": "flux2",
        "steps": 25, "cfg": 3.0, "sampler": "er_sde", "scheduler": "simple",
    },
    "krea2": {
        "unet": "moodyKrea2MixUncensoredV8FREEV8_v80_nvfp4.safetensors",
        "clip": "qwen3vl-4b-abliterated_fp8_e4m3fn.safetensors",
        "clip_type": "krea2",
        "clip_device": "cpu",
        "vae": "qwen_image_vae.safetensors",
        "latent": "sd",
        "steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple",
    },
}

ARMS = ["raw", "t2t", "c2c"]


def build(user_prompt, seed, tag, backend, t2t_text=None, c2c_text=None, pair=None, live=False):
    b = BACKENDS[backend]
    latent_cls = "EmptyFlux2LatentImage" if b["latent"] == "flux2" else "EmptyLatentImage"
    wf = {
        "2": {"class_type": "UNETLoader", "inputs": {
            "unet_name": b["unet"], "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": b["clip"], "type": b["clip_type"], "device": b["clip_device"]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": ""}},
        "8": {"class_type": latent_cls, "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "10": {"class_type": "VAELoader", "inputs": {"vae_name": b["vae"]}},
    }
    if live:
        wf["1"] = {"class_type": "C2CCompare", "inputs": {
            "user_prompt": user_prompt, "max_new_tokens": 256,
            "mode": "both", "pair": pair}}
        t2t_src, c2c_src = ["1", 0], ["1", 1]
    else:
        assert t2t_text is not None and c2c_text is not None, "need texts file for embedded mode"
        t2t_src, c2c_src = t2t_text, c2c_text
    wf["4"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": user_prompt}}
    wf["5"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": t2t_src}}
    wf["6"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": c2c_src}}

    sampler = {
        "model": ["2", 0], "negative": ["7", 0], "latent_image": ["8", 0],
        "seed": seed, "steps": b["steps"], "cfg": b["cfg"],
        "sampler_name": b["sampler"], "scheduler": b["scheduler"], "denoise": 1.0,
    }
    pos_nodes = {"raw": "4", "t2t": "5", "c2c": "6"}
    for i, arm in enumerate(ARMS):
        sid = str(11 + i)
        wf[sid] = {"class_type": "KSampler",
                   "inputs": dict(sampler, positive=[pos_nodes[arm], 0])}
        did = str(14 + i)
        wf[did] = {"class_type": "VAEDecode", "inputs": {"samples": [sid, 0], "vae": ["10", 0]}}
        pid = str(17 + i)
        wf[pid] = {"class_type": "SaveImage", "inputs": {
            "images": [did, 0], "filename_prefix": f"exp_v2/{tag}/{arm}"}}
        lid = str(20 + i)
        wf[lid] = {"class_type": "AddLabel", "inputs": {
            "image": [did, 0], "text_x": 10, "text_y": 2, "height": 64,
            "font_size": 40, "font_color": "white", "label_color": "black",
            "font": "FreeMonoBoldOblique.otf", "text": arm.upper(), "direction": "up"}}
    wf["23"] = {"class_type": "ImageConcanate", "inputs": {
        "image1": ["20", 0], "image2": ["21", 0], "direction": "right", "match_image_size": True}}
    wf["24"] = {"class_type": "ImageConcanate", "inputs": {
        "image1": ["23", 0], "image2": ["22", 0], "direction": "right", "match_image_size": True}}
    wf["25"] = {"class_type": "SaveImage", "inputs": {
        "images": ["24", 0], "filename_prefix": f"exp_v2/{tag}/labeled"}}
    return wf


def write(wf, tag, backend):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{tag}_{backend}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False)
    print(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=list(BACKENDS), required=True)
    ap.add_argument("--live", action="store_true", help="use C2CCompare node at runtime")
    ap.add_argument("--pair", default="qwen3_0.6b+qwen2.5_0.5b")
    ap.add_argument("--texts", default=None, help="bridge batch output JSON (embedded mode)")
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tag", default="pilot")
    ap.add_argument("--matrix", action="store_true")
    ap.add_argument("--seeds", default="42,1042,2042")
    ap.add_argument("--prompt-ids", default="all")
    ap.add_argument("--tag-prefix", default="", help="e.g. A_moss_")
    args = ap.parse_args()

    if args.live:
        assert args.prompt, "--prompt required in live mode"
        wf = build(args.prompt, args.seed, args.tag, args.backend,
                   pair=args.pair, live=True)
        write(wf, args.tag, args.backend)
        return

    texts_path = args.texts or os.path.join(TEXTS_DIR, f"{args.pair}.json")
    data = json.load(open(texts_path, encoding="utf-8"))
    by_id = {it["id"]: it for it in data["items"]}

    if args.matrix:
        items = json.load(open(PROMPTS_FILE, encoding="utf-8"))
        if args.prompt_ids != "all":
            keep = set(args.prompt_ids.split(","))
            items = [it for it in items if it["id"] in keep]
        seeds = [int(s) for s in args.seeds.split(",")]
        for it in items:
            t = by_id[it["id"]]
            for seed in seeds:
                tag = f"{args.tag_prefix}{it['id']}_s{seed}"
                wf = build(it["prompt"], seed, tag, args.backend,
                           t2t_text=t["t2t"]["text"], c2c_text=t["c2c"]["text"])
                write(wf, tag, args.backend)
    else:
        t = by_id[args.tag] if args.tag in by_id else by_id.get(next(iter(by_id)))
        wf = build(t["user_prompt"], args.seed, args.tag, args.backend,
                   t2t_text=t["t2t"]["text"], c2c_text=t["c2c"]["text"])
        write(wf, args.tag, args.backend)


if __name__ == "__main__":
    main()
