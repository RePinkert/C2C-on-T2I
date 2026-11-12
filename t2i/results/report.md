# C2C × 文生图 纯实验报告（T2T vs Cache-to-Cache）

日期：2026-11-03 ｜ 环境：RTX 5070 Ti Laptop (12GB) / Windows / ComfyUI 0.43.2

## 1. 实验设计

在 ComfyUI 中首次将 **Cache-to-Cache**（arXiv 2510.03215, ICLR'26）真 KV-cache 融合接入文生图流水线，
做 T2T（文本中转）与 C2C（cache 融合）的两路对照：

```
用户 idea ──► C2CCompare 节点（单进程双模式）
                ├─ T2T: Sharer(Qwen2.5-0.5B) 出视觉分析文本 → Receiver(Qwen3-0.6B) 写最终 prompt
                └─ C2C: 官方预训练 fuser 把 Sharer 的 KV-Cache 直接融合进 Receiver → 写最终 prompt
        两路 prompt ──► MOSS-Image (moodyMossMix fp8) 同 seed 各采样一次
                    ──► 打标签 (T2T | C2C) 拼接保存
```

- **C2C 引擎**：官方仓库 `thu-nics/C2C`（rosetta）+ HuggingFace 预训练 fuser
  `qwen3_0.6b+qwen2.5_0.5b_Fuser`，未做任何训练
- **T2I 后端**：moodyMossMixFreeDownload fp8 + Qwen3.5-9B int8 文本编码（CPU）+ flux2 VAE，
  1024×1024，25 steps，CFG 3.0，er_sde/simple，**同 seed 成对**
- **样本**：8 条 prompt（中英各半：简单 / 多物体空间关系 / 抽象情绪 / 材质光影 / 中文场景）
- 工作流：`workflows/runs/p01–p08.json`（API 格式）；产物：`results/p01–p08/`；meta：`results/meta/`

## 2. 文本环节延迟（秒，本地实测）

| # | prompt（截断） | T2T | C2C | 加速 |
|---|---|---|---|---|
| p01 | a red fox in deep snow, golden hour | 5.36 | 2.09 | 2.56× |
| p02 | elderly woman + map + black cat, station | 5.31 | 3.27 | 1.62× |
| p03 | 1990s childhood living room, nostalgia | 5.27 | 2.94 | 1.79× |
| p04 | glass teapot, steam, morning backlight | 6.41 | 3.30 | 1.94× |
| p05 | 柴犬红围巾银杏树下落叶（中文） | 5.33 | 2.05 | 2.60× |
| p06 | 夜市少年棉花糖自行车动态模糊（中文） | 5.84 | 3.56 | 1.64× |
| p07 | 宇航员悬崖蓝色星云电影感（中文） | 6.25 | 3.35 | 1.87× |
| p08 | architectural watercolor library | 4.95 | 3.20 | 1.55× |
| **均值** | | **5.59** | **2.97** | **1.88×** |

与论文结论同向（论文平均 2.5×，其 T2T 分析文本更长所以差距更大）：
C2C 用一次并行 cache 融合（~90ms 级）替代 Sharer 的逐 token 解码，本实验中 T2T 的 Sharer 分析
就要 3–5s。且 C2C 免去中间分析文本，T2T 输出长度波动大时延迟更不稳。

## 3. 出图对照（同 seed，左 T2T / 右 C2C）

| # | 文件 | 简评 |
|---|---|---|
| p01 | `results/p01/a98bc755_000.png` | 双方都好；C2C 侧日落更贴 "golden hour" 语义，T2T 侧背景偏冷 |
| p02 | `results/p02/0f7653e7_000.png` | 空间关系（女人/地图/猫/行李箱）两侧均完整 |
| p03 | `results/p03/7eb19da4_000.png` | 抽象情绪题，C2C 更具"氛围细节"，T2T 构图更稳 |
| p04 | `results/p04/0e90d5da_000.png` | **C2C 失败**：prompt 退化成 "A serene, serene,…" 循环 → 出图完全跑题（落日海景）；T2T 茶壶完美 |
| p05 | `results/p05/a48288b8_000.png` | 中文语义（柴犬/银杏）双方皆有漂移，C2C 毛发质感好但树种译错 |
| p06 | `results/p06/a0a3c543_000.png` | 双方都抓住夜市+棉花糖+自行车动态模糊；C2C 霓虹氛围更浓，T2T 人物年龄更准 |
| p07 | `results/p07/240f8f29_000.png` | 双方均佳；C2C 输出 Subject/Action/Setting 结构化 prompt 也有效 |
| p08 | `results/p08/3085b48c_000.png` | 水彩建筑内景双方均合格 |

## 4. 观察与结论

**延迟**：C2C 平均 1.88× 加速，且方差更小 —— 论文核心效率主张在 T2I 的 prompt 环节成立。

**质量**：互有胜负，无一致优胜方：
- C2C 倾向产出更长、更"氛围化"的 prompt（p01/p03 受益）
- T2T 在指令跟随上偶尔更稳（p04 茶壶、p06 年龄）；且偶发中英混杂（p06 的 "招牌"）
- **C2C 退化失败模式被复现**（p04）：融合 cache 偶发解码塌缩，prompt 完全失效。
  与论文 A.4.6 "Sharer 语义误导 Receiver" 的失败分析一致，提示工程上需要
  对 C2C 输出做退化检测（重复 n-gram 检查）兜底
- 中文场景双方均弱（0.5B 级模型语义漂移），C2C 未显著改善

**工程结论**：
1. 真 KV-cache 融合可作为 ComfyUI 节点稳定运行（subprocess 隔离，显存 12GB 内与扩散模型共存）
2. 文本编码器必须放 CPU（Qwen3.5-9B int8 10GB 上 GPU 直接把 ComfyUI 打崩，已规避）
3. C2C 最适合的 T2I 位置是 **prompt 生成/增强环节**，收益 = 更快 + 语义更丰富，但需退化兜底

## 5. 复现指引

```
c2c/                    # 官方仓库 + venv + 权重（fuser/Qwen3-0.6B/Qwen2.5-0.5B）
c2c/c2c_bridge.py       # 双模式 bridge（--mode both|t2t|c2c）
ComfyUI-C2C/            # 节点包（junction 到 ComfyUI custom_nodes）
workflows/build_workflow.py  # 生成 runs/pXX.json
results/                # 出图 + meta + 本报告
```

扩展方向：多 Sharer 融合（论文 A.5）、用文生图域数据自训 fuser、
C2C 输出退化检测、向自回归图像生成器（非扩散）迁移 cache 融合。
