# 盲评（第二轮 / round 2）

> 第一轮（n=3，仅 raw_vs_c2c）的全部数据已作废并删除。本目录描述第二轮。

## 协议（2026-11-05 定稿）

- **形式**：公开 GitHub Pages 单页应用 `https://repinkert.github.io/C2C-on-T2I/`
  （从 `/docs` 发布 + `.nojekyll`，静态直出；图池 `docs/pool/`，252 张无标签原 PNG）
- **抽样**：**每次打开页面，浏览器熵随机重抽**。从 84 cells 中抽 21 对：
  raw_vs_c2c / raw_vs_t2t / t2t_vs_c2c 各 7 对，**21 个 prompt 互不重复**；
  每场顺序与左右全随机，中英大致均衡
- **作答存储**：**不用 localStorage**；作答只存标签页内存，**刷新/关闭即清空**
  （未提交/未导出时 `beforeunload` 会弹浏览器确认框）
- **任务**：每对两问，三选一（左图 / 相当 / 右图）：
  1. 忠实度：哪张更符合文字描述？
  2. 观感：哪张更好看？

## 自动回收（2026-11-05 新增）

- 答完 **21/21** 后 "提交结果" 按钮变绿；点击 → 确认框（提交后不可修改）→ 自动 POST 到
  Google Apps Script → **追加进私密 Google Sheet `blind_votes`**（只有表主可见）
- 脚本只写不读：校验必须正好 42 行、字段白名单（`id` 形如 `p##_s####`、`q`、`answer`、`left/right` 对应的处理），
  不匹配的请求一律拒收；Sheet 行按 `submission_id | seq | submitted_at | nickname | pair_id | q | answer | truth_left | truth_right` 排列（长表）
- 只收：昵称（可空，≤30 字）、提交时间、42 票；**不收 IP / UA / 任何指纹**
- Sheet URL 公开（静态页内嵌），**无法根治垃圾行**；对策：脚本白名单 + 表主人眼ball 出 `submitted_at` 前后的脏行删掉即可
- **匿名自愿、无验证码、无去重**——被刷 / 伪造在理论上可能，解读限 aggregate 趋势
- 网络失败时返回错误并保留 **导出 CSV** 按钮兜底（手动回传亦可）
- 提交成功页面显示"你是第 N 位受访者"（N = 该 Sheet 已有的完整问卷份数 + 1）

## 分析口径（重要）

因**每位受访者看到的 21 对都是随机抽取、互不相同**：

- aggregate 胜率按**汇总票数**做 binomial 检验（faith / look 分开报），并同时给"相当计半"口径
- **聚类校正**：同一 prompt 会被多人、多问重复评，票级 p 会高估显著性。以 prompt 为单位
  （26–27 条）补做 sign test 与 Wilcoxon signed-rank，结论以两者一致为准
  （`eval/analyze_robust.py` → `results/metrics/votes_robust.md|csv`）
- **分语种**（prompts_v2.json 的 lang 字段：zh 12 / en 16）单独报胜率与聚类检验，
  并做 2×2 Fisher 交互检验；不要用小样本子集的相关差异直接下结论
- **κ 仍不可评估**：n=11 下每个 comparison×q 组里 ≥2 人共评的 item 只有 17–20 个，
  两两一致率 .31–.59，且存在 rater 对全选"相当"使 κ 无定义。可报一致率，不报 κ

## 回收后

从 Sheet 导出 `blind_votes` 为 CSV → 拼成 `results/blind/votes_*.csv` →

```powershell
python eval/analyze_votes.py --votes results/blind/votes_*.csv
python eval/analyze_robust.py --votes results/blind/votes_*.csv   # 聚类校正/分语种/重叠度/相似度
```

产出写入 `results/metrics/votes_summary.md|csv`；按 `report/report_final.md`「人评」一节更新结论并重新生成 `report/figures/fig_blind.png`。
