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

- aggregate 胜率按**汇总票数**做 binomial 检验（faith / look 分开报）
- **κ（Cohen's kappa，跨受访者同 item 一致性）不可计算**——人均仅评 21 对且各不同
- per-item 统计因样本稀疏也不做；只报三比较 × 两问的胜率与相当比例

## 回收后

从 Sheet 导出 `blind_votes` 为 CSV → 拼成 `results/blind/votes_*.csv` →

```powershell
python eval/analyze_votes.py --votes results/blind/votes_*.csv
```

产出写入 `results/metrics/votes_summary.md|csv`；按 `report/report_final.md`「人评」一节更新结论并重新生成 `report/figures/fig_blind.png`。
