# EXPERIMENT_DESIGN — v2 研究级实验设计

> 配套 `HANDOFF.md`。目标：对外/研究型汇报。所有设计决策已与用户确认
> （研究型汇报 / 完整研究级 / 自动+人工盲评 / 不做增量亮点包装）。

## 1. 实验矩阵

| 因子 | 取值 | 角色 |
|---|---|---|
| 通信臂 arm | `raw`（原始 prompt 直出）/ `t2t`（Sharer 文本中转）/ `c2c`（KV-cache 融合） | 组内因子 |
| 模型对 pair | ① `qwen3_0.6b+qwen2.5_0.5b`（主）② `qwen3_0.6b+qwen3_4b_base`（强 base Sharer） | 泛化因子 A |
| T2I 后端 backend | ① `moss`（moodyMossMix fp8）② `krea2`（moodyKrea2MixUncensoredV8 nvfp4） | 泛化因子 B |
| prompt | 16 条（中英各半；类型：简单/多物体空间/抽象情绪/材质光影/中文场景/风格复合） | 样本 |
| seed | 3 个 / prompt（三臂同 seed 成对） | 重复 |

**运行量（图像生成）**
| 矩阵 | 覆盖 | 图数 | run 数 | 估时 |
|---|---|---|---|---|
| 主 | pair① × moss × 3臂 × 16 prompt × 3 seed | 144 | 48 | ~3.2h |
| 泛化 A | pair② × moss × 3臂 × 8 prompt(子集) × 3 seed | 72 | 24 | ~1.6h |
| 泛化 B | pair① × krea2 × 3臂 × 8 prompt(子集) × 3 seed | 72 | 24 | ~1.6h |
| 合计 | | 288 | 96 | **~6.5h** |

子集选择：p01–p08（v1 已有图的 prompt，便于纵向对比）。

**prompt 生成**（便宜，先跑）：2 pair × 2 臂(t2t/c2c) × 16 prompt = 64 次 bridge 生成，
用 `--batch` 一次加载跑完，估 <30min。raw 臂无 LLM。

## 2. 公平性修复（相对 v1）

1. **修 T2T 截断**：Sharer 分析预算 96→256 tokens；三臂最终 prompt 输出预算统一 256
2. **延迟口径**：`--batch` 稳态延迟（纯生成）为主指标；冷启动（含模型加载 ~7s）单列
3. **退化样本保留**：单列 `degenerate` 类别；指标报"含/不含退化"两套
4. **成本记录**：每次批跑记录 GPU 时数

## 3. 自动指标

| 维度 | 指标 | 工具 | 说明 |
|---|---|---|---|
| 忠实度（主） | CLIP score（图 vs **用户原始 prompt**） | open_clip ViT-L/14 | 防增强后偏离用户意图 |
| 自洽性 | CLIP score（图 vs 增强后 prompt） | 同上 | C2C prompt 更长的混杂因素 |
| 观感 | LAION aesthetic V2 | aesthetic-predictor | |
| 文本退化 | rep-4gram 率、distinct-1/2/3 | bridge 自算 | p04 类失败的量化 |
| 文本质量 | 语言纯净度（中英混杂检测）、长度 | text_stats | |
| 效率 | 稳态/冷启动延迟、token 数 | bridge 输出 | |

**统计**：每比较 n=48（16 prompt × 3 seed）配对；Wilcoxon signed-rank + bootstrap 95% CI +
effect size（Cliff's delta 或 matched-pairs rank-biserial）。显著性阈值 p<0.05 双尾。

**可选消融（P1）**：把三臂 prompt 截断到等 token 数重比一次 → 分离"语义增益 vs 长度增益"。

## 4. 人工盲评协议

- **刺激**：无标签单图对（同 prompt 同 seed，t2t vs c2c；raw vs best）。左右顺序随机化
- **样本**：每比较 20 对（从 48 对中分层抽样，覆盖各 prompt 类型）
- **任务**：三选一（左 / 右 / 相当）× 2 问题：
  1. 忠实度：哪张更符合文字描述？
  2. 观感：哪张更好看？
- **实施**：`eval/make_blind_html.py` 生成本地 HTML（含隐藏映射），评完导出 CSV
- **分析**：胜率（排除"相当"与含"相当"两套）、二项检验、评估者间一致性（Cohen's κ，≥2 人时）

## 5. 失败分析（RQ3）

- 退化样本全收录（不修不删），统计：退化率（按臂/按 pair）、触发特征（prompt 类型？长度？）
- 案例 gallery：v1 的 p04 + v2 新增
- 对照论文 A.4.6（Sharer 语义误导）与解码退化两类失败的异同

## 6. 汇报材料结构（report_final.md + figures）

1. TL;DR + RQ（§1 of HANDOFF）
2. Background：C2C 原理 1 页（KV-cache 融合 vs T2T，引论文）
3. Method：系统架构图（工作流框图）、模型配置表
4. Setup：矩阵表、指标定义、盲评协议、统计方法
5. Results：延迟图（冷/热分离）、CLIP/美学箱线图+显著性表、盲评胜率、泛化表（pair2/krea2）
6. Failure analysis：退化 gallery + 频率
7. Limitations：0.5B 级小模型、fuser 在 QA 数据上训练而本任务零样本迁移、单机 n 有限、
   C2C prompt 更长的混杂
8. Conclusion + Future work（文生图域自训 fuser、多 Sharer、更大模型对）
9. 附录：复现手册（HANDOFF §2 坑清单）、原始数据表

## 7. Krea2 后端参数（pilot 校准项）

moodyKrea2Mix 系配方未知。起点：模板 turbo 默认（8 steps，cfg 1.0，euler/simple，1024²），
TE 用 `qwen3vl-4b-abliterated_fp8_e4m3fn`（type `krea2`，**可上 GPU**，4.5GB）或 CPU。
pilot 判据：人物/场景不崩、风格正常 → 固化参数进 build_workflow.py。

## 8. 产物与命名约定

```
results\
├── exp_v2\{tag}\           # tag = {arm}_{pair}_{backend}_{prompt}_{seed}
│   ├── {tag}_raw.png       # 无标签单图（盲评用）
│   ├── {tag}_t2t.png
│   ├── {tag}_c2c.png
│   └── {tag}_labeled.png   # 带标签拼接（展示用）
├── meta\c2c_meta_*.json    # bridge 输出（v2 起含退化统计、pair 标识）
├── metrics\*.csv           # 指标长表
└── blind\blind.html + votes.csv
```

工作流文件：`workflows/runs_v2/{tag}.json`（API 格式，一 run 一 prompt-seed）。
