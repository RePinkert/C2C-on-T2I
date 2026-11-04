"""Image metrics: CLIP score (user + enhanced prompt) and LAION aesthetic.

Usage: python run_eval.py --manifest ..\\results\\metrics\\manifest.csv
Writes results/metrics/image_metrics.csv. Requires open_clip_torch + torch.
"""
import argparse
import csv
import os

import torch
from PIL import Image


def load_clip():
    import open_clip
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="openai")
    tokenizer = open_clip.get_tokenizer("ViT-L-14")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return model.to(device).eval(), preprocess, tokenizer, device


def load_aesthetic():
    """LAION aesthetic V2 head (sa_0_4_vit_l_14_linear = nn.Linear(768,1)) on ViT-L/14."""
    import open_clip
    from torch import nn
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="openai")
    head = nn.Linear(768, 1)
    head_path = os.path.join(os.path.dirname(__file__), "sa_0_4_vit_l_14_linear.pth")
    if not os.path.exists(head_path):
        raise FileNotFoundError(
            f"missing aesthetic head: {head_path} — download "
            "sa_0_4_vit_l_14_linear.pth (LAION aesthetic predictor V2)")
    head.load_state_dict(torch.load(head_path, map_location="cpu"))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return model.to(device).eval(), head.to(device).eval(), preprocess, device


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-aesthetic", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.manifest, encoding="utf-8-sig")))
    clip_model, preprocess, tokenizer, device = load_clip()
    if args.no_aesthetic:
        aes_model = aes_mlp = aes_pre = None
    else:
        aes_model, aes_mlp, aes_pre, _ = load_aesthetic()

    out_rows = []
    for r in rows:
        path = r["image_path"]
        rec = {"tag": r["tag"], "arm": r["arm"], "prompt_id": r["prompt_id"],
               "seed": r["seed"], "pair": r["pair"], "backend": r.get("backend", ""),
               "image_path": path}
        if not path or not os.path.exists(path):
            rec["clip_user"] = rec["clip_enhanced"] = rec["aesthetic"] = ""
            out_rows.append(rec)
            continue
        img = Image.open(path).convert("RGB")
        x = preprocess(img).unsqueeze(0).to(device)
        image_features = clip_model.encode_image(x)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        for key, txt in (("clip_user", r["user_prompt"]),
                         ("clip_enhanced", r["enhanced_prompt"])):
            t = tokenizer([txt]).to(device)
            tf = clip_model.encode_text(t)
            tf = tf / tf.norm(dim=-1, keepdim=True)
            rec[key] = round(float((image_features @ tf.T).item()), 4)

        if aes_model is not None:
            xa = aes_pre(img).unsqueeze(0).to(device)
            feat = aes_model.encode_image(xa)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            rec["aesthetic"] = round(float(aes_mlp(feat).item()), 4)
        out_rows.append(rec)

    out = args.out or os.path.join(os.path.dirname(args.manifest), "image_metrics.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"{len(out_rows)} rows -> {out}")


if __name__ == "__main__":
    main()
