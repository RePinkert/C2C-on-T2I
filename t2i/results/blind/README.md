# 盲评（第二轮 / round 2）

> 第一轮（n=3，仅 raw_vs_c2c）的全部数据已作废并删除。本目录描述第二轮。

## 协议（2026-11-05 定稿）

- **形式**：公开 GitHub Pages 单页应用
  `https://repinkert.github.io/C2C-on-T2I/`，从 `/docs` 发布（`docs/`，已带 `.nojekyll`，静态直出）
- **抽样**：**每次打开页面，用浏览器熵随机重抽一份全新问卷**。
  - 从 84 个 (prompt × seed) cell 中抽 **21 对**：raw_vs_c2c / raw_vs_t2t / t2t_vs_c2c 各 7 对
  - **21 个 prompt 互不重复**；每个比较内部语言（中英）比例大致均衡（≥2 中文）
  - 出场顺序与左右位置全部随机
- **作答存储**：**不用 localStorage**。所有作答只存于当前标签页内存，**刷新/关闭即清空**
  （有未导出作答时 `beforeunload` 会弹浏览器确认框）。页面底部注明此点。
- **任务**：每对两问，三选一（左图 / 相当 / 右图）：
  1. 忠实度：哪张更符合文字描述？
  2. 观感：哪张更好看？
- **评估者**：群组志愿者，昵称自愿（仅用于区分问卷，不展示、不分析身份）
- **导出**：答完点"导出 CSV"得到 `votes_<昵称>_<时间戳>.csv`（列：id,prompt,q,answer,truth_left,truth_right），
  格式与 `eval/analyze_votes.py` 直接兼容
- **分析口径**：因**每个受访者看到的 21 对随机抽取、彼此不同**，aggregate 臂胜率按
  **汇总票数**（binomial test）给出；**κ（Cohen's kappa，跨受访者同 item 一致性）不可计算**
  （人均仅评 21 对、重叠极稀疏），报告中如实说明。per-item 统计因票数稀疏也不做。
- **防刷/去重**：静态页面无任何去重手段——匿名、自愿、可重复作答；解读以 aggregate 趋势为限。
  映射内嵌（原图即盲评素材，诚实地说：view-source 可解，受访者多为非技术背景）。

## 回收后

```powershell
python eval/analyze_votes.py --votes results/blind/votes_*.csv
```

产出写入 `results/metrics/votes_summary.md|csv`（含三比较的 raw/t2t/c2c 臂胜率）；
按 `report/report_final.md`「人评」一节更新结论并重新生成 `report/figures/fig_blind.png`。
