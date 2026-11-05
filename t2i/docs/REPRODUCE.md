# 复现手册（C2C × 文生图，v2）

> 目标：在**你自己的机器**上复现本仓库 `t2i/report/report_final.md` 的全部数字。
> 英文速览见 `t2i/README.md`；本文为完整中文版，含全部已知坑。

## 0. 硬件与前提

- NVIDIA GPU ≥ 12GB 显存（实测 RTX 5070 Ti Laptop / 12GB，Windows 11；Linux 应更顺）
- RAM ≥ 16GB（大文本编码器放 CPU；不足 16GB 会很痛苦）
- 已安装 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 并能正常出图
- 约 20GB 磁盘（fuser ×2 + Qwen3-0.6B / Qwen2.5-0.5B / Qwen3-4B-Base ≈ 12GB + T2I 权重）
- 两个 T2I 后端所用的**社区微调 checkpoint**（moodyMossMix fp8、moodyKrea2MixUncensoredV8 nvfp4）
  不在本仓库，需自行下载，**注意各自许可证**；它们不是复现 C2C 本身所必需，只是我们选的出图模型。

## 1. Python 环境（最重要：transformers 必须钉 4.52.4）

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -U pip
venv\Scripts\python.exe -m pip install transformers==4.52.4 datasets==3.6.0 huggingface_hub==0.31.1 peft==0.15.2
venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu128
```

- rosetta（C2C 推理包）依赖旧版 `DynamicCache.key_cache` API；`pip install peft` 会把
  transformers 拉到 5.x 直接崩。**装完任何包之后再确认一次 `transformers` 版本没被动过。**
- uv 不认 `venv` 目录名 → 用 `uv pip install --python venv\Scripts\python.exe ...`
- 图像指标还需要：`open_clip_torch`、`scipy`、`matplotlib`、`pillow`、`numpy`

## 2. 下载权重（HF 直连可用，无需镜像）

```powershell
cd t2i
..\venv\Scripts\python.exe download_models.py
```

依次下载：`nics-efc/C2C_Fuser`（pairA 与 pairB 两个 fuser）+ `Qwen/Qwen3-0.6B`、
`Qwen/Qwen2.5-0.5B-Instruct`、`Qwen/Qwen3-4B-Base`（HF 公开仓库）。直连失败会自动回退
`hf-mirror.com`。权重落在 `t2i/models/`（已在 .gitignore，勿提交）。

冒烟测试（约 15s，GPU）：

```powershell
..\venv\Scripts\python.exe smoke_test.py
```

## 3. ComfyUI + 节点

1. 把 `t2i/ComfyUI-C2C` 复制（或 junction）到 ComfyUI 的 `custom_nodes/` 目录；
2. 重启 ComfyUI（新节点注册需要重启）；
3. 若节点报 `c2c_bridge.py not found`，设置环境变量 `C2C_ROOT` 指向本仓库 `t2i/` 目录；
   节点内 `VENV_PY` 指向装好依赖的 venv（见 nodes.py 顶部注释）。

## 4. 后端配置（已固化，复现实验用这个）

| 后端 | 配置 |
|---|---|
| moss（主矩阵 + 泛化A） | moodyMossMix fp8 + **Qwen3.5-9B int8 TE（必须 CPU，上 GPU 会 OOM 硬崩）** + flux2-vae；1024²，25 steps，CFG 3.0，er_sde/simple |
| krea2（泛化B） | moodyKrea2MixUncensoredV8nvfp4 + qwen3vl-4b-abliterated fp8 TE + qwen_image_vae；1024²，8 steps，CFG 1.0，euler/simple（turbo 配方） |

MOSS 架构是 `layers.*`（不是 Krea2 的 `blocks.*`），CLIPLoader type 用 `moss_image`、Krea2 用 `krea2`。

## 5. 生成工作流并批跑

```powershell
cd t2i
..\venv\Scripts\python.exe workflows\build_workflow.py   # 生成 workflows/runs_v2/*.json（3 种处理 × 2 后端 × 双输出）
```

- **文本/图像已解耦**：`runs_v2/*.json` 把 t2t/c2c 文本作为**字面量**嵌入，图像批跑零 LLM；
  文本批量生成在 bridge 侧完成（`results/prompts_generated/pairA|B.json`，含延迟与退化统计）。
- 批跑：先启动 ComfyUI（默认 `127.0.0.1:8188`），再 `python workflows\run_batch.py`
  （内置断点续跑；日志写到 `results/batch_log.txt`）。
- 96 run ≈ 过夜级别（每 run 3 图 × ~4min/张，CPU TE 编码为主）。

## 6. 评估流水线

```powershell
cd t2i
# 1) manifest + 文本统计（泛化矩阵只跑了 p01–p08，注意 pid 范围参数）
..\venv\Scripts\python.exe eval\collect.py --texts results\prompts_generated\pairA.json results\prompts_generated\pairB.json --matrices A_moss_:pairA:moss B_moss_:pairB:moss:p01-p08 A_krea2_:pairA:krea2:p01-p08
# 2) CLIP ViT-L/14 + LAION aesthetic V2（首次运行自动下载美学线性头）
..\venv\Scripts\python.exe eval\run_eval.py --manifest results\metrics\manifest.csv
# 3) Wilcoxon + bootstrap CI
..\venv\Scripts\python.exe eval\stats.py --metrics results\metrics\image_metrics.csv
# 4) 盲评页（无标签单图 + 左右随机；导出 CSV；单页含三比较各 7 对）
..\venv\Scripts\python.exe eval\make_blind_html.py --manifest results\metrics\manifest.csv --mixed 7,7,7 --out results\blind\blind_compare_all.html
# 5) 汇总盲评（胜率 + 二项检验 + Cohen's κ）
..\venv\Scripts\python.exe eval\analyze_votes.py --votes results\blind\votes_*.csv
# 6) 全部图表
..\venv\Scripts\python.exe eval\make_figs.py
```

## 7. 血泪坑清单（务必先读）

1. **transformers 钉 4.52.4**；别让 peft 把它拉到 5.x。
2. **大 TE 必须 CPU**（Qwen3.5-9B int8 上 GPU 直接把 ComfyUI 打崩，日志断在 “10000MB Staged”）。
3. 生成的对比图带 T2T/C2C 标签（展示用）；**盲评必须用无标签原图**。
4. JSON 保存为 **UTF-8 无 BOM**（BOM 曾导致 A_moss_p01_s1042 首跑失败，已补跑）。
5. 断点续跑的文件名匹配已修（DONE 行带耗时后缀）；重跑前先看 `results/batch_log.txt`。
6. 中文 prompt 是 C2C 退化重灾区（v3：p08/p10/p14/p24 等中文提示塌缩，p09 弱重复；另有 p21 英文儿童绘本塌缩）：0.6B 级 Receiver 在融合表征下中英漂移出元语言。
7. **退化兜底**（上线前必需）：distinct-2 < 0.35（n>20）或 rep-4gram > 0.25 → 回退 T2T；v3 退化率 7/56 = 12.5%，不可裸奔上线。p06（结构化泄漏 Subject:/Action:/Setting:）可被该阈值完全漏检，需人工抽查。
8. HF 直连可用（无需镜像）；git clone 的 stderr 进度条会让 PowerShell 报 NativeCommandError，无害。
9. 图像批跑与文本批跑解耦后，改 prompt 不必重跑图；改种子/后端才需要重跑对应矩阵。
10. 盲评第二轮：单页 21 对，覆盖 raw_vs_c2c / raw_vs_t2t / t2t_vs_c2c 三个 pairwise 各 7 对；第一轮（n=3，仅 raw_vs_c2c）已作废。不要把本报告的人评结论外推到未测批次。

## 8. 期望结果

- 文本稳态延迟：pairA **2.17×**（8.02s→3.70s），pairB **3.44×**（11.89s→3.46s）；
- C2C 退化率 **7/56 = 12.5%**（pairA: p08/p10/p14/p21/p24；pairB: p09/p24），T2T 0；
- 人评 raw > C2C（忠实度 85%，观感 72%）；LAION aesthetic 则 C2C 胜（与人评矛盾，见报告（人评一节））；
- 全部原始数字：`t2i/report/report_final.md`；图：`t2i/report/figures/`。
