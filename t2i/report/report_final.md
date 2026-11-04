# C2C × 文生图 实验报告（v2）

> 把 Cache-to-Cache（KV-Cache 直传，arXiv 2510.03215 / ICLR'26）接进 ComfyUI 文生图 prompt
> 生成环节，和文本中转（T2T）、raw 基线做对照。日期：2026-11-04。
> 环境：RTX 5070 Ti Laptop (12GB) / Windows / ComfyUI 0.43.2，推理零训练（官方预训练 fuser）。
> 数据在 `results/metrics/`，图在 `report/figures/`。

## 先说做这件事的经过

论文这套东西的核心是让两个 LLM 直接融合 KV-Cache 传递语义，替代"Sharer 先解码出分析文本、
Receiver 再读"的文本中转。论文自己的数字是通信延迟平均快 2.5×。我们想知道这个收益放到文生图
管线里还成不成立，以及要不要为它支付图像质量的代价。论文 A.4.6 提过 Sharer 语义误导 Receiver
的失败模式，但没人在生成式视觉任务上实测过。

第一版只跑了 8 个 prompt，跑完发现两个问题。T2T 那条路上，Sharer 的分析写到 96 个 token
就被截断在半句，T2T 吃亏；另外量太小了，n=8、单 seed，也没做统计，这样的数当不了结论。
第二版就把这些全补上了：三条臂的 token 预算统一成 256，prompt 扩到 16 条、每条配 3 个 seed，
再加 raw 基线、第二个 Sharer 对、第二个 T2I 后端和人工盲评。统计按 prompt 和 seed 配对，
Wilcoxon 检验加 bootstrap。

## 我们做了什么

三臂对照：raw（用户 idea 直接喂 T2I）、t2t（Sharer 分析 → 文本中转 → Receiver 写 prompt）、
c2c（Sharer 前向一次出 KV-Cache → 预训练 fuser 融进 Receiver → 写 prompt）。模型配置：

| 组件 | pairA（主） | pairB（泛化 A：强 Sharer） |
|---|---|---|
| Receiver | Qwen3-0.6B | Qwen3-0.6B |
| Sharer | Qwen2.5-0.5B-Instruct | Qwen3-4B-Base |
| Fuser | `qwen3_0.6b+qwen2.5_0.5b_Fuser` | `qwen3_0.6b+qwen3_4b_base_Fuser` |
| 三臂 token 预算 | 统一 256（v1 的 96 截断对 T2T 不公平，已修） | 同左 |

| T2I 后端 | 配置 |
|---|---|
| moss（主+泛化A） | moodyMossMix fp8 + Qwen3.5-9B int8 TE（**TE 必须 CPU**，上 GPU 会 OOM 崩）+ flux2-vae；1024²，25 steps，CFG 3.0，er_sde/simple |
| krea2（泛化B） | moodyKrea2MixUncensoredV8 nvfp4 + qwen3vl-4b-abliterated fp8 TE（CPU）+ qwen_image_vae；1024²，8 steps，CFG 1.0，euler/simple |

文本/图像解耦：prompt 由 bridge 批量生成（`results/prompts_generated/pairA|B.json`，含延迟与
退化统计），图像批跑把文本作字面量嵌入工作流，零 LLM 调用，三臂 prompt 完全受控。

实验矩阵：

| 矩阵 | 覆盖 | run 数 | 图数 | 用途 |
|---|---|---|---|---|
| 主矩阵 | pairA × moss × 16 prompt × 3 seed | 48 | 144 | RQ1–RQ3（n=48 配对） |
| 泛化 A | pairB × moss × p01–p08 × 3 seed | 24 | 72 | 跨 Sharer 对 |
| 泛化 B | pairA × krea2 × p01–p08 × 3 seed | 24 | 72 | 跨 T2I 后端 |

16 条 prompt（中英各半；简单单体 / 多物体空间 / 抽象情绪 / 材质光影 / 中文场景 / 风格复合），
seed 42/1042/2042，三臂同 seed 成对。96 个 run 全部完成，0 缺失，共 288 张图。

指标三个：clip_user（图 vs 用户原始 prompt，主指标，防增强后偏离意图）、clip_enhanced（图 vs
增强后 prompt，用来暴露 C2C 长文本带来的长度混杂）、aesthetic（LAION V2）。文本侧统计
rep-4gram / distinct-1/2/3 退化率、稳态/冷启动延迟、token 数。统计按 (prompt, seed) 配对，
Wilcoxon signed-rank 双尾 + bootstrap 2000 次 95% CI + matched-pairs rank-biserial，显著性 p<0.05。

人工盲评原定两个比较（t2t_vs_c2c、raw_vs_c2c）。两份问卷发出去之前我们自己先看了一眼无标签
单图对。c2c 和 t2t 画出来的图几乎分不出，就只挑了 raw_vs_c2c 一份送群组，t2t 臂因此没有
人评数据。每对两问（忠实度/观感）三选一，多评估者独立投票，导出 CSV 后用
`eval/analyze_votes.py` 汇总。

## 先把结论说在前头

文本环节快 1.74×（pairA）到 9.05×（pairB），Sharer 越强越快。图像质量上，raw 显著优于两个
增强臂（clip_user），两个增强臂彼此分不出；aesthetic 是唯一往 C2C 方向倒的指标。C2C 有
3/16 的 prompt 解码塌缩（T2T 为 0），p04/p15 跨 pair 复现。人评 raw 占优。

放在一起看：加速是真的，质量代价主要是"增强偏离意图"（两增强臂共同的问题），C2C 独有的坑是
解码塌缩。下面逐项说。

## 延迟

![latency](figures/fig_latency.png)

| | 冷启动 load | T2T 稳态 | C2C 稳态 | 加速 |
|---|---|---|---|---|
| pairA（Sharer 0.5B） | 5.84s | 5.94s ± 1.75 | 3.42s ± 2.17 | 1.74× |
| pairB（Sharer 4B-Base） | 16.07s | 34.19s ± 9.69 | 3.78s ± 2.55 | 9.05× |

口径：文本批全 16 prompt 的稳态均值 ± std；冷启动为模型加载耗时，一次性。

T2T 的成本随 Sharer 变大而暴涨。pairB 的 Sharer 分析要 ~32s；C2C 的融合成本几乎不随 Sharer
变大，稳态 3.42s（pairA） / 3.78s（pairB）。Sharer 越强，文本中转越是瓶颈，C2C 的收益越大。
这和论文报的 2.5× 同向，在强 Sharer 下还放大了。

token 数也顺便看了一下：C2C 的 prompt 更长（pairA 84 vs 47，pairB 68 vs 37，预算同为 256），
延迟优势不是靠少说话换来的。

端到端我们得诚实说一句：单张扩散图 ~4min，文本环节省下的 2.5–30s 在一次性出图场景占比不到
8%。C2C 的价值在交互式 prompt 预览、多候选筛选（文本环节在关键路径上）和批量管线上，不在
单次出图上。

## 图像质量

![quality](figures/fig_quality.png)

主矩阵（pairA@moss，n=48 配对）：

| metric | 对比 | diff | 95% CI | p | 结论 |
|---|---|---|---|---|---|
| clip_user | raw vs t2t | +0.0072 | [0.002, 0.012] | 0.004 | raw 更贴用户意图 |
| clip_user | raw vs c2c | +0.0172 | [0.008, 0.029] | 0.002 | raw 更贴用户意图 |
| clip_user | t2t vs c2c | +0.0099 | [-0.001, 0.023] | 0.332 | 两增强臂无显著差异 |
| clip_enhanced | t2t vs c2c | +0.0281 | [0.017, 0.039] | <0.001 | t2t 与自身文本更自洽 |
| aesthetic | t2t vs c2c | -0.1966 | [-0.368, -0.021] | 0.012 | c2c 观感更优 |
| aesthetic | raw vs c2c | -0.2509 | [-0.481, -0.035] | 0.013 | c2c 观感更优 |

逐项说：

- clip_user 三行：raw > t2t（p=0.004）、raw > c2c（p=0.002）、t2t ≈ c2c（p=0.332）。两个增强臂
  都把图拉离了用户意图，没看出谁拉得更多。clip_enhanced 上 t2t 显著更优（p<0.001）。同样的
  内容，t2t 和自己写的文本更合拍。aesthetic 上 c2c 显著更优（p=0.012），raw 也输了（p=0.013）。
- 长度混杂确实存在：C2C prompt 长 ~1.8×，只看 clip_enhanced 会误判 t2t 胜出；把 clip_user 设为
  主指标就是为了分开"语义增益"和"长度增益"。不过反过来也不成立，把 C2C 的低 clip_enhanced 全
  算到长度头上说不过去，它的 clip_user 也确实偏低。
- 「增强即漂移」是两个臂共同的问题，和通信方式无关。clip_user 两臂都显著差于 raw。
- aesthetic 这一格（c2c 更优）是三个矩阵里唯一自动指标往 c2c 方向倒的地方，而在人评里方向
  刚好反过来（见下），不要拿它吹"更好看"。

## 泛化

| 指标 | 主矩阵 pairA@moss | 泛化A pairB@moss | 泛化B pairA@krea2 |
|---|---|---|---|
| clip_user t2t vs c2c | +0.010 n.s. | +0.020 p=0.095 | +0.020 n.s. |
| clip_enhanced t2t vs c2c | +0.028 p<0.001 | +0.004 n.s. | +0.038 p<0.001 |
| aesthetic t2t vs c2c | -0.20 p=0.012（c2c 胜） | +0.10 p=0.079 | -0.05 n.s. |
| C2C 退化率 | 3/16 | 3/16 | （复用 pairA 文本） |

延迟收益两个 pair、两个后端都成立。质量这边不稳：pairB 上美学优势没了（甚至反转 +0.10，
p=0.079），krea2 上打平（-0.05，n.s.）。主矩阵那个 p=0.012 是 moss × pairA 的现象，
n=24 的泛化矩阵下不该外推。clip_user 三个矩阵都是 t2t ≥ c2c，方向一致，但均不显著或仅边缘，
这个指标至少没变坏。退化模式 pairA/pairB 都复现了。

## 人评

只送审了 **raw_vs_c2c** 一份问卷（`results/blind/blind_raw_vs_c2c.html`，20 对，单文件自包含）；
t2t_vs_c2c 未送审，t2t 臂没有人评数据。评估者 3 人（A、B、C，群组志愿者），
每人 20 对 × 2 问 = 40 票，共 120 票，无缺失。汇总见 `results/metrics/votes_summary.md|csv`。

| 问题 | raw 胜 | c2c 胜 | 相当 | 胜率 raw（排相当） | 胜率 raw（相当计半） | binomial p | mean κ |
|---|---|---|---|---|---|---|---|
| 忠实度 faith | 41 | 7 | 12 | 0.854 | 0.783 | <0.001 | 0.208 |
| 观感 look | 36 | 14 | 10 | 0.720 | 0.683 | 0.0026 | 0.061 |

![blind](figures/fig_blind.png)

三个人的票：faith — A 15/3/2、B 11/1/8、C 15/3/2；look — A 12/7/1、
B 9/4/7、C 15/3/2。方向一致。B 相当票明显偏多（faith 8/20），和"两臂图像输出几乎
分不出"这个体感一致。

忠实度人评 raw 占优（85%，p<0.001），和 clip_user（raw > c2c，p=0.002）一个方向。C2C 增强后
确实更偏离用户原始意图。观感 raw 也占优（72%，p=0.003），和 LAION aesthetic 反了方向。自动
美学头给出的"c2c 更好看"和人眼不是一回事，LAION 分数不能单独当"好看"的证据。

κ 只有 0.06–0.21，相当率偏高（faith 20%、look 17%）。这组人评证据只能支持到"raw 不劣于
c2c、大概率更优"这个程度，给不出更精确的胜率估计。

对"质量有没有代价"的结论：C2C 相对 T2T 没有显示出任何一致的质量劣化，但也看不出人眼可见的
增益。"aesthetic 更优"是那个自动指标自己的偏好。

复现：见 `docs/REPRODUCE.md`（公开版为 fork 仓库的 `t2i/docs/REPRODUCE.md`）；
相关脚本是 `eval/analyze_votes.py` 和 `eval/make_figs.py`。

## 失败模式

![degenerate](figures/fig_degenerate.png)

C2C 解码塌缩 3/16 = 18.75%（pairA: p04/p07/p15；pairB: p04/p13/p15），T2T 为 0。有图的退化样本
全收在 `report/figures/gallery/`（seed 42，带标签拼接图）；pairB 的 p13/p15 属文本批独有，没有
对应图。四个案例：

| 案例 | 类型 | rep-4gram | 表现 | 跨 pair |
|---|---|---|---|---|
| p04 玻璃茶壶 | 循环塌缩 | 0.984 | "A serene, serene, …"×25 → 出图完全跑题（落日海景） | ✅ 两 pair 同输出 |
| p15 场景插画 | 元语言自指 | 0.056/0.102 | "A detailed English image generation prompt: 'A detailed…'" 递归嵌套 | ✅ 两 pair 均触发 |
| p07 宇航员（中文） | 结构化泄漏+局部重复 | 0.564 | "Subject:/Action:/Setting:" 格式泄漏 + "flowing robes and flowing robes" | 仅 pairA |
| p13 早市（中文） | 局部短语重复 | 0.436 | "steaming/steamed" 同义反复 | 仅 pairB |

p04/p15 稳定复现在同一批 prompt 上，说明这不是随机噪声，是 prompt 触发的。p04 是"材质光影+
静物"类，p15 是"风格复合长描述"。它们和论文 A.4.6 的"Sharer 语义误导 Receiver"同源（融合表征
偶发把 Receiver 解码带进死循环），但复现位置固定这件事论文没展开。

中文 prompt 是重灾区（p07/p13/p15 均中文）：0.6B 级 Receiver 在融合表征下容易中英混杂、漂移出
元语言。T2T 中文也有语义漂移，但不塌缩。

工程兜底的方向：C2C 输出必须挂退化检测（rep-4gram > 0.5 或 distinct-1 < 0.5 时回退 T2T）。
当前检测器能吃下全部 6 个退化样本，误伤率还没查。

## 局限

1. 0.5B–4B 级 LLM + 5B 级 DiT，结论不能外推到 GPT 级 Sharer 或大型 T2I。
2. fuser 在 QA 数据上训练，文生图域完全 zero-shot，没做微调。
3. 主矩阵 n=48、泛化 n=24，单机单 seed。美学预测器（LAION 线性头）本身有偏好。
4. 长度混杂只用 clip_user/clip_enhanced 粗部分离，等 token 截断消融没做（P1 可选项，未做）。
5. 人评只测了 raw_vs_c2c，3 名群组志愿者、每比较 20 对；t2t 臂没有人评证据；κ 弱、相当率偏高。
6. 文本环节在扩散管线里不是瓶颈。这套方案的落地场景是交互式预览 / 批量管线，不是单次出图。

## 接下来想做的

如果再往下推一步：先在文生图域数据上自训（或对齐）fuser，看看退化率能不能压下来；工程上把
退化检测 + T2T 回退做成混合管线；多 Sharer 融合（论文 A.5）做 prompt 生成的"专家委员会"；
补等 token 截断消融；试试 >4B Sharer 的延迟曲线；甚至把 cache 融合迁移到自回归图像生成器
（文本-图像联合 KV 空间）上。

## 附录：原始数据与复现

| 文件 | 内容 |
|---|---|
| `results/metrics/manifest.csv` | 288 图 × 路径/prompt/arm/矩阵 |
| `results/metrics/image_metrics.csv` | clip_user / clip_enhanced / aesthetic |
| `results/metrics/text_stats.csv` | 延迟/token/退化统计（64 行文本臂） |
| `results/metrics/stats_pairs.csv` + `stats_summary.md` | 配对 Wilcoxon 全表 |
| `results/metrics/votes_summary.csv` | 盲评汇总（raw_vs_c2c × 忠实度/观感，3 人） |
| `results/prompts_generated/pairA|B.json` | 三臂原始 prompt + 延迟明细 |
| `results/batch_log.txt` | 96 run 批跑日志（含补跑记录） |
| `report/figures/gallery/` | 退化案例图（带标签拼接） |

复现手册见 `docs/HANDOFF.md`（公开版见 fork 仓库的 `t2i/docs/REPRODUCE.md`）。
