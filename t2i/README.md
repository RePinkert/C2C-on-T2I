# t2i — Cache-to-Cache for Text-to-Image Prompt Generation

A complete, reproducible toolchain that applies **Cache-to-Cache (C2C)** — the
KV-cache fusion paradigm from [arXiv:2510.03215](https://arxiv.org/abs/2510.03215)
(ICLR'26) — to the **prompt-generation stage of text-to-image pipelines**
(ComfyUI), and evaluates it against the text-relay baseline (T2T) and a raw
(no-enhancement) baseline.

> This directory is an **addition by this fork**; the upstream repository is unchanged.
> C2C fuses the Sharer's KV-cache into the Receiver via a pretrained, frozen
> fuser — zero training, zero fine-tuning.

## What's inside

```
t2i/
├── c2c_bridge.py          # ★ core: dual-mode (T2T / C2C) prompt generator
├── download_models.py     # fetches pretrained fuser + Qwen weights from HF
├── smoke_test.py          # fuser smoke test (~15s on GPU)
├── ComfyUI-C2C/           # ComfyUI custom node (C2CCompare): T2T vs C2C in one box
├── workflows/             # workflow JSONs (runs/ v1, runs_v2/ v2: 3 arms × 2 backends)
│                          #   + build_workflow.py / run_batch.py generators & batch runner
├── eval/                  # evaluation harness
│   ├── collect.py         #   manifest + text stats
│   ├── run_eval.py        #   CLIP ViT-L/14 + LAION aesthetic-v2
│   ├── stats.py           #   Wilcoxon signed-rank + bootstrap 95% CI
│   ├── make_blind_html.py #   blind A/B page generator (self-contained HTML)
│   ├── analyze_votes.py   #   multi-evaluator votes → win rate + binomial test + Cohen's κ
│   └── make_figs.py       #   report figures
├── docs/
│   ├── EXPERIMENT_DESIGN.md
│   └── REPRODUCE.md       # ★ 复现手册（中文，含全部踩坑清单）
├── results/               # manifest / metrics / per-arm prompts (small CSVs & JSONs)
└── report/
    ├── report_final.md    # ★ full experiment report (中文)
    └── figures/           # fig_latency / fig_quality / fig_blind / fig_degenerate + gallery
```

## Headline results (v2, 96 runs / 288 images, zero failures)

| Question | Answer |
|---|---|
| Latency? | C2C text stage **1.74×** faster (pairA, Sharer 0.5B) and **9.05×** (pairB, Sharer 4B); scales with Sharer size |
| Image quality? | No consistent degradation. LAION aesthetic favors C2C on moss×pairA (p=0.012) but does **not** replicate on pairB/krea2; T2T wins self-consistency (clip_enhanced, p<0.001) |
| User-intent alignment? | Both enhancement arms drift from the raw user prompt equally (clip_user); C2C is **not** worse than T2T (n.s.) |
| Failure modes? | C2C decode collapse **3/16 (18.75%)** on both pairs (T2T: 0/16) — repetition loops, meta-language self-reference, phrase duplication; **requires rep-4gram / distinct-n guard + T2T fallback** |
| Human blind eval? | raw beats C2C on faithfulness (85%, p<0.001) and looks (72%, p=0.003); LAION aesthetic head disagrees with humans — see the report's blind-eval section |
| Generalization? | Latency win replicates across fuser pairs and T2I backends; quality conclusions only partially replicate; degeneration reproduces on both pairs |

Details, statistics and honest negative results: **[report/report_final.md](report/report_final.md)**.

## Reproduce

See **[docs/REPRODUCE.md](docs/REPRODUCE.md)** (Chinese). Short version:

1. Python env with `transformers==4.52.4` (**must be pinned**), `datasets==3.6.0`,
   `huggingface_hub==0.31.1`, `peft==0.15.2`;
2. `python t2i/download_models.py` (pulls fuser + Qwen3-0.6B / Qwen2.5-0.5B-Instruct / Qwen3-4B-Base);
3. Install [ComfyUI](https://github.com/comfyanonymous/ComfyUI); drop `t2i/ComfyUI-C2C` into
   `custom_nodes/`; restart; set `C2C_ROOT` if the node can't locate `c2c_bridge.py`;
4. Large text encoders must run on **CPU** (10GB int8 TE OOMs 12GB cards);
5. Generate workflows via `t2i/workflows/build_workflow.py`, batch-run with
   `t2i/workflows/run_batch.py`, then run the eval pipeline (`collect → run_eval → stats`).

Hardware used for the reported numbers: RTX 5070 Ti Laptop (12GB), Windows 11, ComfyUI.
Image stage is ~4 min/image (CPU TE encoding dominates); the text stage decouples from it.

## Known limitations

- **18.75% degeneration rate** in C2C outputs (T2T: 0). Always gate on rep-4gram > 0.5 /
  distinct-1 < 0.5 and fall back to T2T in production.
- fuser is **zero-shot** for the T2I domain (trained on QA); no fine-tuning was applied.
- 0.5B–4B-class models; conclusions do not extrapolate to frontier models.
- Blind eval: one comparison (raw_vs_c2c), 3 volunteer evaluators; κ weak (0.06–0.21).
  Evaluator identities are anonymized in this public copy.
- The t2t_vs_c2c blind page was never sent out (the two pages were near-indistinguishable);
  no human judgment exists for that pair.

## License & attribution

Upstream C2C (this repository) is **Apache License 2.0**; the `t2i/` additions are
offered under the same license. See [`../LICENSE`](../LICENSE). The paper:

```bibtex
@article{fu2025c2c,
  title={Cache-to-Cache: Direct Semantic Communication Between Large Language Models},
  author={Fu, Tianyu and Min, Zihan and Zhang, Hanling and Yan, Jichao and Dai, Guohao and Ouyang, Wanli and Wang, Yu},
  journal={arXiv preprint arXiv:2510.03215},
  year={2025}
}
```

This is an independent community evaluation, **not affiliated with or endorsed by the
paper's authors**. Bugs in `t2i/` are ours — please file issues on this fork.
