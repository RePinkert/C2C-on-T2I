# 盲评（第二轮 / round 2）

> 第一轮（n=3，仅 raw_vs_c2c，两问卷图像输出几乎不可区分）的全部数据已作废并删除，
> 汇总表与盲评图也已随仓库清理。本目录只描述第二轮。

## 协议

- **刺激**：`C2C-on-T2I/t2i/blind/blind_compare_all.html`（单文件自包含，无外部依赖）
  - 21 对**无标签**单图对；**21 个 prompt 互不重复**
  - 三种 pairwise 比较各 7 对：`raw_vs_c2c` / `raw_vs_t2t` / `t2t_vs_c2c`
    （每 prompt 配一个 seed，`42 / 1042 / 2042` 各出现 7 次）
  - 主矩阵 = pairA（Sharer Qwen2.5-0.5B-Instruct）× moss 后端
  - 左右顺序随机化，映射隐藏于页面内部（不展示给受访者）
- **任务**：每对两问，三选一（左图 / 相当 / 右图）：
  1. 忠实度：哪张更符合文字描述？
  2. 观感：哪张更好看？
- **评估者**：群组志愿者，昵称自愿输入（仅用于区分问卷，不展示、不分析身份）
- **数据管理**：作答只存于受访者浏览器 localStorage（无上传、无后端）；完成后点"导出 CSV"
  下载 `votes_<昵称>_<时间戳>.csv`，发回给主持人即可
- **局限**：页面为静态文件，无法去重——同一人可重复作答；自愿、匿名、无支付；
  左右映射埋在文件里，技术用户可 view-source 解码（接受该取舍，评估者均非技术背景志愿者）
- **分析**：`eval/analyze_votes.py`（胜率两套口径 + 二项检验 + Cohen's κ，支持三种比较混跑）

## 回收后

```powershell
python eval/analyze_votes.py --votes results/blind/votes_*.csv
```

产出写入 `results/metrics/votes_summary.md|csv`；按 `report/report_final.md`「人评」一节更新结论，
并重新生成 `report/figures/fig_blind.png`。
