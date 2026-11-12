# HANDOFF — C2C × 文生图 研究型实验（入口文档）

> **新线程从这里开始读。** 读完本文件 + `EXPERIMENT_DESIGN.md` 即可无缝续作。
> 最后更新：2026-11-09（盲评第二轮累计回收 n=11 / 462 票，全部汇总与图表已按新数据重算，n=4 旧结论已删除；报告人评节扩写为聚类校正 + 分语种 + 机制分析；fork 尚未同步本轮更新）

## 0. 一句话状态

v3 全量重跑**全部完成**：28 条手工 prompt（7 基准+7 中文直译+7 换媒介+7 短句，中英 16/12），
132 run 批跑补齐（0 缺失，396 图）、CLIP/美学指标、分矩阵统计。盲评第一轮（n=3）已作废删除；
第二轮动态单页 `https://repinkert.github.io/C2C-on-T2I/` 已发布 fork（`docs/`）。
**第二轮累计回收：n=11 / 462 票（2026-11-05 至 11-06；昵称 9 空 2 填，42/42×11，三比较×两问各
77 票）。raw 在两项比较中领先：raw>c2c 忠实度 38:10（.79，p<.0001）、观感 38:13（.75，p=.0006）；
raw>t2t 忠实度 37:6（.86，p<.0001）、观感 34:16（.68，p=.015）；t2t vs c2c 无差异（.449/.407，
p=.57/.22）。以 prompt 为单位的聚类校正后仍成立（raw>t2t 16:0 sign p<.0001；raw>c2c 15:5 sign p=.041,
Wilcoxon p=.021）。raw 的优势集中在中文输入（raw>c2c 中文 26:4 vs 英文 12:6，后者 42 票中 24 票「相当」）；
机制上一是英文增强≈复述（Jaccard .66/.70）、中文增强是整句重写（.002/.004）。**
（n=4 阶段的「raw~t2t n.s.」旧结论已随样本扩充作废删除；κ 仍不可估——≥2 人共评 item 仅 17–20 个。）
`report/report_final.md` 为论坛级 A 版（MICE 主导 I）：图表编号（图 1–5 / 表 1–10），§3.4 已扩写为
票级 + 聚类级 + 分语种 + 文本相似度四层证据。**fork 尚未同步本轮（report/figures/votes_* 的本地改动未推送）。**
（设计约束不变：不加"退化兜底 demo / 强 Sharer 亮点包装"，强 Sharer 仅作泛化维度。）

## 1. 项目是什么

arXiv 2510.03215《Cache-to-Cache: Direct Semantic Communication Between LLMs》(ICLR'26)
提出用 KV-Cache 融合（神经投影+门控）替代文本中转，实现 LLM 间语义直传。
本项目把它接入 **ComfyUI 文生图工作流的 prompt 生成环节**，对照 T2T（文本中转）评估
延迟与图像质量。真 KV-cache 融合用官方预训练 fuser（零训练），rosetta 代码推理。

**研究问题（汇报主线）**
- RQ1 C2C 加速是否以图像质量为代价？
- RQ2 对"图像-用户意图对齐"的影响（防 C2C 靠加长 prompt 自嗨）？
- RQ3 失败模式与频率（已观测到解码退化案例）？
- RQ4 跨 Sharer / 跨 T2I 后端是否泛化？

## 2. 环境事实（勿重复踩坑）

| 项 | 值 |
|---|---|
| GPU | RTX 5070 Ti Laptop，**12GB VRAM**，Blackwell（torch **2.11.0+cu128** / torchvision 0.26.0+cu128） |
| RAM | 16GB（偏紧，大 TE 必须放 CPU） |
| ComfyUI | `C:\cc\ComfyUI_windows_portable\ComfyUI`，端口 8188，comfy-cli 1.18.0 |
| C2C 源码 | `C:\Yet\C2C-on-T2I`（上游 thu-nics/C2C 已并入本仓库；`upstream/main` + `upstream/context` 两个远程引用保留上游历史） |
| 运行时 | `C:\Yet\C2C-on-T2I\runtime`（权重 models + venv；`script`/`rosetta` 是指向仓库的 junction） |
| 节点包 | `C:\Yet\C2C-on-T2I\t2i\ComfyUI-C2C`（custom_nodes 里是 junction 指向它，改代码即生效但需重启 ComfyUI） |
| 工作区 | `C:\Yet`（`C2C-on-T2I` 项目已移出 Playground；`Playground\` 下只剩 `bench` 基准） |

**已知坑（血泪清单）**
1. **transformers 必须钉 4.52.4**：rosetta 依赖旧版 `DynamicCache.key_cache` API；
   `pip install peft` 会把它拉到 5.x 直接崩。配套 `datasets==3.6.0 huggingface_hub==0.31.1 peft==0.15.2`
2. **Qwen3.5-9B 文本编码器（10GB int8）上 GPU 会把 ComfyUI 打崩**（OOM 硬崩，日志断在
   "10000MB Staged"）。MOSS 后端的 `CLIPLoader` 必须 `device: "cpu"`
3. MCP `run_workflow(wait=True)` / `job(wait)` 在长任务上会客户端超时 → 一律
   `run_workflow(wait=False)` + `job(action="status"/"queue")` 轮询
4. MCP `launch_comfyui` 返回超时 ≠ 失败，等 20-30s 再探 `http://127.0.0.1:8188/system_stats`
5. HF 直连可用（无需镜像）；git clone 的 stderr 进度条会让 PowerShell 报 NativeCommandError，无害
6. uv 不认 `venv\` 目录名 → 用 `uv pip install --python venv\Scripts\python.exe ...`
7. **Windows 上 `uv pip install torch` 默认装 CPU 版**，bridge 报 "Torch not compiled with CUDA
enabled"。修法：`uv pip install --python venv\Scripts\python.exe torch torchvision --index-url
https://download.pytorch.org/whl/cu128 --reinstall-package torch torchvision`
（torch 2.11.0+cu128 / torchvision 0.26.0+cu128；transformers 钉 4.52.4 不受影响）
8. 队列里有历史遗留 job 记录（prompt_enhancer_*.json），状态陈旧，忽略
9. 生成的对比图带 T2T/C2C 标签（展示用）；**盲评必须用无标签原图**

## 3. 文件地图

```
C:\Yet\
├── C2C-on-T2I\                # ★ 唯一代码真相源（上游 C2C 源码 + t2i 工具链 + runtime）
│   ├── script\ rosetta\ recipe\ bash\ resource\   # 上游 C2C 源码（= upstream/main）
│   ├── docs\                 # GitHub Pages：盲评池 pool\ + pool.json
│   ├── runtime\              # 运行时资产（★ 不在 git 追踪内）
│   │   ├── models\           # Qwen3-0.6B / Qwen2.5-0.5B-Instruct / Qwen3-4B-Base / c2c_fuser
│   │   ├── venv\             # Python 环境（uv 管理，无 pip）
│   │   ├── script\  rosetta\ # junction → 仓库根
│   │   └── c2c_bridge.py smoke_test.py download_models.py  # hardlink → t2i\
│   └── t2i\                  # ★ 本实验的全部产物都在这里
│       ├── c2c_bridge.py      # ★ 双模式（t2t/c2c）prompt 生成 bridge（ROOT 走 C2C_ROOT）
│       ├── smoke_test.py      # fuser 冒烟
│       ├── download_models.py # 权重下载（可重跑，增量）
│       ├── ComfyUI-C2C\       # 节点包（nodes.py: C2CCompare）→ custom_nodes junction 指向这里
│       ├── workflows\
│       │   ├── build_workflow.py     # ★ 工作流生成器（3 处理×2 后端×双输出；--matrix/--prompt-ids）
│       │   ├── run_batch.py          # ★ 批跑器（断点续跑，DONE 行带耗时后缀会跳过）
│       │   ├── krea2_t2i_base.json   # gallery 模板（参考）
│       │   ├── moss_t2i_base.json    # gallery 模板（参考）
│       │   └── runs_v2\*.json         # 134 份实际跑批配置
│       ├── prompts_v2.json    # ★ 28 条手工 prompt（7基准+7中文直译+7换媒介+7短句，zh 12/en 16）
│       ├── eval\
│       │   ├── collect.py            # manifest + text_stats（--matrices 支持 pid 范围）
│       │   ├── run_eval.py           # CLIP ViT-L-14 + LAION 美学
│       │   ├── stats.py              # 分矩阵 Wilcoxon + bootstrap CI
│       │   ├── make_blind_html.py    # 盲评页（--pair/--backend 过滤；署名导出）
│       │   ├── analyze_votes.py      # 多评估者 votes 汇总（胜率+二项检验+κ）
│       │   ├── analyze_robust.py     # 聚类校正(sign/Wilcoxon)+分语种+重叠度+文本相似度
│       │   ├── make_figs.py          # report/figures/ 全部图表 + 退化 gallery
│       │   └── legacy\               # 归档：mixed 模式旧版 make_blind_html.py
│       ├── results\
│       │   ├── report.md             # v1 报告（已有结论与观察）
│       │   ├── prompts_generated\    # pairA/B.json：三种处理的文本+延迟+退化统计（v3：28 prompt）
│       │   ├── metrics\              # manifest 396 行 0 缺失/image_metrics/text_stats/stats_summary
│       │   #    votes_summary（n=11 汇总）/votes_robust（聚类+分语种+相似度）
│       │   #    （第二轮盲评页已迁入 fork docs\，本页 = https://repinkert.github.io/C2C-on-T2I/）
│       │   ├── blind\                # 原始导出 CSV + votes_1..11_（匿名拆分，mio/Susan 带昵称）+ 已废弃 html
│       │   └── meta\c2c_meta_*.json  # 每次 bridge 运行的 prompt/延迟记录
│       ├── exp_v2\            # ComfyUI 产出图 528 张（1.1GB，已 gitignore，可重跑生成）
│       ├── report\
│       │   ├── report_final.md       # ★ 论坛级 A 版（MICE 主导 I；图表编号；人评已并入）
│       │   └── figures\              # fig_latency/quality/blind/blind_lang/degenerate + gallery
│       └── docs\
│           ├── HANDOFF.md            ← 本文件
│           ├── EXPERIMENT_DESIGN.md  ← v2 实验矩阵/指标/盲评协议/预算
│           └── _archive\             # v2 归档（prompts_v2_v1_16.json.bak、report_final_v2.md）
└── Playground\
    └── bench\                 # 自定义 benchmark（独立仓库）
```

## 4. 已完成（v1，2026-11-03）

- 官方 C2C 推理跑通（fuser `qwen3_0.6b+qwen2.5_0.5b_Fuser`，GPU，~15s 冒烟）
- `C2CCompare` 节点注册进 ComfyUI 并可被 MCP 调用
- 两路对照工作流（MOSS-Image: moodyMossMix fp8 + qwen3vl?→**实为 qwen3.5_9b int8 CPU**
  + flux2-vae；1024²，25 steps，CFG 3.0，er_sde/simple）
- 8 prompt 批跑完成，v1 结论（见 `results/report.md`）：
  - 文本环节延迟 **T2T 5.59s vs C2C 2.97s（1.88×）**
  - 图像质量互有胜负；**C2C 退化失败案例 p04**（"A serene, serene,…" 循环→出图跑题）
  - 中文 prompt 双方均有语义漂移
- **v1 方法学缺陷（v2 必须修）**：T2T 的 Sharer 分析被 max_new_tokens=96 截断在半句
  （不公平，削弱了 T2T）；缺 raw 基线；n=8 单 seed 无统计

## 5. 进度

> S0–S10 为 v2 阶段（已全部完成；产物已被 v3 取代或删除）；以下 S11/S12 为当前 v3 状态。

- [x] **S0 文档**：本文件 + EXPERIMENT_DESIGN
- [x] **S1 bridge v2**：token 预算统一 256；`--batch`；`--pair`；退化统计（rep-4gram/distinct-n）
- [x] **S2 权重**：pair② fuser + Qwen3-4B-Base 已下载并冒烟（C2C 生成 3.55s）
- [x] **S3 prompts_v2.json**：16 条
- [x] **S4 build_workflow.py v2**：3 种处理 × 2 后端 × 双输出（无标签单图+带标签拼接）；
      **文本/图像解耦**：批量实验模式把 t2t/c2c 文本作为字面量嵌入（图像批跑零 LLM）
- [x] **S5 节点**：C2CCompare 加 `pair` 输入，解析 v2 输出格式
- [x] **S6 pilot**：双后端通过。Krea2 参数固化 = 8 steps cfg 1.0 euler/simple
      （moodyKrea2MixUncensoredV8_nvfp4 + qwen3vl-4b-abliterated fp8 CPU + qwen_image_vae）
- [x] **S7 eval 脚本**：`eval/collect.py`（manifest+文本统计）、`run_eval.py`（CLIP ViT-L-14
      + LAION 美学 Linear 头，头已下载）、`stats.py`（Wilcoxon+bootstrap）、`make_blind_html.py`
- [x] **S8 过夜批跑**：96 run 全部完成（0 缺失）。`run_batch.py` 的断点续跑解析 bug
      （DONE 行带耗时后缀匹配不上文件名）已修；BOM 失败的 A_moss_p01_s1042 已补跑。
      文本已生成：`results/prompts_generated/`pairA.json / pairB.json（含延迟+退化统计）
- [x] **S11 v3 全量重跑**（2026-11-05）：torch 2.14.1+cpu→2.11.0+cu128 修复 bridge；
      prompts 从 16 改 28（手工风格化基准+中文直译+换媒介+短句）；全部旧产物删除；
      bridge ×2 → 132 run batch_log 0 错误；指标：manifest 396/396、主矩阵 n=84、泛化 n=24。
      关键数：pairA T2T 8.02s vs C2C 3.70s（2.17×）；pairB 11.89s vs 3.46s（3.44×；）
      aesthetic 三矩阵全不显著（v2 的 c2c 美学优势未复现）；pairB clip_enhanced 翻转为 c2c 显著
      （p=0.034）；退化 7/56=12.5%（pairA 5：p08/p10/p14/p21/p24；pairB 2：p09/p24），T2T 0；
      p06 结构泄漏（Subject:/Action:/…）检测器漏检（人工发现）
- [x] **S12 盲评第二轮（2026-11-05 定稿，数据截至 2026-11-06）**：动态单页 `docs/index.html`（Pages 发布
      `https://repinkert.github.io/C2C-on-T2I/`）—— **每次打开用 Math.random() 重新随机抽取**
      21 对（raw_vs_c2c / raw_vs_t2t / t2t_vs_c2c 各 7 对，21 prompt 互不重复，顺序/左右全随机，
      中英大致均衡）；**弃用 localStorage**，作答仅存标签页内存，刷新即清空（未提交前 beforeunload
      提醒）；图池 252 张无标签原 PNG（~372MB）推上 fork `docs/pool/`。
      **自动回收**：答完 21/21 → "提交结果"（确认框）→ POST 到 Google Apps Script → 追加进私密
      Sheet `1blbPb4xNV4mk6o9JsyXmRMNHeAZ7XJuzvtDjtnTNMg` 的 `blind_votes` 表（长表，每份 42 行：
      submission_id|seq|submitted_at|nickname|pair_id|q|answer|truth_left|truth_right）；
      只收昵称/时间/42 票，不收 IP/UA；网络失败可"导出 CSV"兜底。
      **分析口径**：aggregate 胜率 + binomial（主），并以 prompt 为单位做聚类校正
      （sign test + Wilcoxon，避免同一 prompt 被多人多问重复评导致 p 高估）；分语种另报。
      κ 仍不可评估——n=11 下每个 comparison×q 组里 ≥2 人共评的 item 仅 17–20 个，
      两两一致率 .31–.59，且有 rater 对全选"相当"使 κ 无定义。
      协议见 fork `t2i/results/blind/README.md`。
      **回收结果（2026-11-09 重算，n=11）**：11 份完整问卷（42/42×11，2026-11-05 至 11-06，
      昵称 9 空 2 填），合计 462 票，三种 pairwise × 两问各 77 票，结构校验通过（无重复 pair/
      缺问项/同臂对比/缺失行）。**raw 在两项比较中领先**：raw>c2c 忠实度 38:10（.79，p<.0001）、
      观感 38:13（.75，p=.0006）；raw>t2t 忠实度 37:6（.86，p<.0001）、观感 34:16（.68，p=.015）；
      **t2t vs c2c 无差异**（.449/.407，p=.57/.22）。聚类校正（prompt 级）后 raw>t2t 忠实度 16:0
      （sign p<.0001）、raw>c2c 忠实度 15:5（sign p=.041、Wilcoxon p=.021）仍成立。
      分语种：raw>c2c 中文 26:4 显著、英文 12:6 n.s.（该格 42 票里 24 票「相当」）。
      Tie 率 36%。原始导出留在 `results/blind/`（私密不公开），匿名汇总
      `results/metrics/votes_summary.md|csv`，稳健性分析 `results/metrics/votes_robust.md|csv`。

### 盲评第二轮回收后命令（已执行，2026-11-09 按 11 月 9 日累积导出重算）

```powershell
cd C:\Yet\C2C-on-T2I\t2i\eval
$py = 'C:\Yet\C2C-on-T2I\runtime\venv\Scripts\python.exe'
& $py sheet_to_votes.py --sheet "..\results\blind\C2C-on-T2I - blind_votes2026年11月9日.csv" --out-dir ..\results\blind
& $py analyze_votes.py  --votes ..\results\blind\votes_*.csv
& $py analyze_robust.py --votes ..\results\blind\votes_*.csv   # 聚类校正/分语种/重叠度/相似度
& $py make_figs.py     # 再生成 fig_blind.png（fig_blind_lang.png 由 analyze_robust 出）
# 报告 §3.4/§5/§6.5 已按 n=11 重写，n=4 旧结论删除；fork 尚未同步推送本轮更新
```

注意：sheet 是**累积追加**导出的，重跑会把 `votes_1..N` 原地覆盖（同名同内容），不会重复计票；
带昵称的会写成 `votes_10_Susan.csv` 这类文件名，`votes_*.csv` 通配仍能匹配。

注意：`analyze_votes.py` 修了一个原有 bug——`votes_summary.csv` 的列名原取自第一行，
跨比较混合时后续行报 `dict contains fields not in fieldnames`；现改为固定列
`raw_wins/t2t_wins/c2c_wins`（缺省 0）。另外 sheet 导出没走 fetch_sheet.py（用户手动导出），
两份累积导出（`...2026年11月5日.csv` / `...2026年11月9日.csv`）原位保留在 `results/blind/`。

### S11/S12 已执行命令（留档）

```powershell
cd C:\Yet\C2C-on-T2I\t2i
$py = 'C:\Yet\C2C-on-T2I\runtime\venv\Scripts\python.exe'
& $py runtime\c2c_bridge.py --batch-file prompts_v2.json --pair "qwen3_0.6b+qwen2.5_0.5b" --mode both --out results\prompts_generated\pairA.json
& $py runtime\c2c_bridge.py --batch-file prompts_v2.json --pair "qwen3_0.6b+qwen3_4b_base" --mode both --out results\prompts_generated\pairB.json
cd workflows
& $py build_workflow.py --matrix --backend moss --texts ..\results\prompts_generated\pairA.json --tag-prefix A_moss_
& $py build_workflow.py --matrix --backend moss --texts ..\results\prompts_generated\pairB.json --prompt-ids p01,p02,p03,p04,p05,p06,p07,p08 --tag-prefix B_moss_
& $py build_workflow.py --matrix --backend krea2 --texts ..\results\prompts_generated\pairA.json --prompt-ids p01,p02,p03,p04,p05,p06,p07,p08 --tag-prefix A_krea2_
Start-Process -FilePath $py -ArgumentList 'C:\Yet\C2C-on-T2I\t2i\workflows\run_batch.py --files "C:\Yet\C2C-on-T2I\t2i\workflows\runs_v2\*.json"' -WindowStyle Hidden -RedirectStandardOutput '..\results\batch_stdout.log' -RedirectStandardError '..\results\batch_stderr.log'
cd ..
$env:COMFY_OUT = 'C:\Yet\C2C-on-T2I\t2i\exp_v2'
& $py eval\collect.py --texts results\prompts_generated\pairA.json results\prompts_generated\pairB.json --matrices A_moss_:pairA:moss B_moss_:pairB:moss:p01-p08 A_krea2_:pairA:krea2:p01-p08
& $py eval\run_eval.py --manifest results\metrics\manifest.csv
& $py eval\stats.py --metrics results\metrics\image_metrics.csv
& $py eval\make_figs.py
# 第二轮页面已改为静态动态单页（docs/index.html + docs/pool/）；旧 make_blind_html.py --mixed 已废弃
```

注意：`make_blind_html.py` 新增 `--mixed N1,N2,N3`（raw_vs_c2c,raw_vs_t2t,t2t_vs_c2c）模式——
单页 21 对、21 条 prompt 互不重复、seed 42/1042/2042 各 7 对，盲评 UI 已重做
（`blind_votes_v2_compare_all` key，打开即空进度）。collect 仍支持 `--matrices prefix:pairkey:backend[:pid-range]`；
stats.py / make_blind_html.py 已修多矩阵混叠 bug。

## 6. 常用命令

```powershell
# C2C bridge（venv）
cd C:\Yet\C2C-on-T2I\runtime
venv\Scripts\python.exe c2c_bridge.py --user-prompt "..." --max-new-tokens 256 --mode both --out C:\Yet\C2C-on-T2I\t2i\results\meta\test.json

# 生成工作流
cd C:\Yet\C2C-on-T2I\t2i\workflows
& 'C:\Yet\C2C-on-T2I\runtime\venv\Scripts\python.exe' build_workflow.py

# ComfyUI：启动（超时正常，等 20-30s）
# 用 MCP launch_comfyui / restart_comfyui；或手动：
# & "C:\cc\ComfyUI_windows_portable\python_embeded\python.exe" "C:\cc\ComfyUI_windows_portable\ComfyUI\main.py" --enable-manager

# 任务轮询（MCP job action=queue / status）
# 产物回收（MCP fetch_outputs prompt_id=... out_dir=...）
```

## 7. 关键实验事实速查

- MOSS 后端 = MOSS-Image 架构（layers.* / text_embedder），**不是 Krea2**（blocks.*）；
  用 `moss_image` CLIPLoader type + `flux2-vae` + `EmptyFlux2LatentImage`
- Krea2 后端 = `krea2` CLIPLoader type + `qwen_image_vae` + `EmptyLatentImage`，
  模板默认 8 steps cfg 1 euler/simple（turbo 系）；可用 unet：
  `moodyKrea2MixUncensoredV8FREEV8_v80_nvfp4.safetensors`（7.7GB，12GB 内可行）
- 图像环节与文本环节解耦：pair 只影响 prompt 生成，图像矩阵可复用 prompt
- 当前实测每张图 ~4min（含 CPU TE 编码），一 run 三种处理各出 1 张图
