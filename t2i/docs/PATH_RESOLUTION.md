---
title: 路径相对化重映射设计
status: 设计稿，待实施
scope: C2C-on-T2I/t2i/（工具链与产物）
out-of-scope: 上游 script/、rosetta/、recipe/（均用 HF repo id 或包内相对路径，无本地绝对路径）
---

# 路径相对化重映射设计（PATH_RESOLUTION）

## 1. 现状盘点

### 1.1 锚点概念：三个并存，含义重叠

| 概念 | 实际位置 | 谁在用 |
|---|---|---|
| `t2i/` | 工具链 + 产物的根 | eval 脚本、workflows 脚本 |
| `runtime/` | 权重 + venv（未追踪） | bridge、smoke_test、节点包 |
| 仓库根 | 上游源码 + t2i + runtime | 节点包（想找 t2i 却只能靠 env） |

### 1.2 解析方式：7 种并存

| # | 模式 | 使用者 |
|---|---|---|
| A | `dirname(__file__)` 上溯 N 层 | analyze_robust(2)、analyze_votes(2)、collect(2)、make_figs(2)、make_blind_html(2)、sheet_to_votes(2)、run_batch(2)、build_workflow(1) |
| B | `C2C_ROOT` env → 回退 `<repo>/runtime` | c2c_bridge、smoke_test、nodes.py |
| C | `PLAYGROUND` env → 回退 `dirname²(__file__)` | collect、make_blind_html |
| D | `EXP_OUT_DIR` env | make_figs |
| E | `COMFY_OUT` env | collect |
| F | 由 `--manifest` 位置上溯推导根 | run_eval、make_blind_html |
| G | 硬编码绝对路径 | eval/legacy/make_blind_html_mixed.py |

问题：同一语义 7 种表达；模式 A 的上溯层数因文件位置而异（`t2i/eval/` 需 2 层、`t2i/eval/legacy/` 需 3 层）；模式 F 使行为取决于调用时的工作目录。

### 1.3 环境变量：4 个名字表达同一件事

`PLAYGROUND`、`COMFY_OUT`、`EXP_OUT_DIR`、`C2C_ROOT` —— 实际都在指"项目在哪"。
其中 `COMFY_OUT`（collect.py）与 `EXP_OUT_DIR`（make_figs.py）指向同一个 `exp_v2/`；`PLAYGROUND` 这个名字已名不副实（现在指 `t2i/`，不是 Playground 目录）。

### 1.4 真实绝对路径泄漏（已跟踪文件）

严格扫描（盘符+反斜杠，排除正则转义误报）后，**只有 3 处**真实泄漏：

| 文件 | 处数 | 性质 |
|---|---|---|
| `t2i/results/batch_list.txt` | 96 | 真实泄漏：96 条工作流绝对路径 |
| `t2i/eval/legacy/make_blind_html_mixed.py` | 1 | 真实泄漏：`PLAYGROUND = r"C:\Yet\Playground"`（该目录已不存在） |
| `t2i/docs/HANDOFF.md` | 17 | 文档中的机器特定路径（ComfyUI 安装位置等） |

> `rosetta/*`、`script/*` 的命中全部是 `\s`、`\n` 正则/JSON 转义误报，无真实泄漏。

---

## 2. 目标与硬约束

| 编号 | 目标 |
|---|---|
| G1 | 一个语义一个名字：锚点只保留 `PROJECT_ROOT` / `T2I_ROOT` / `RUNTIME_ROOT` 三层 |
| G2 | 存储期与运行期分离：文件里存相对路径，运行时才绝对化 |
| G3 | junction 穿透：节点包经 `custom_nodes/ComfyUI-C2C`（junction）加载时，`__file__` 字面量在 ComfyUI 安装目录，仍须能定位仓库（**实测 `Path.resolve()` 已可穿透，见 §4.3**） |
| G4 | 克隆即可用：`runtime/` 不在版本库，缺失时给出可执行的报错而非 FileNotFoundError |
| G5 | 向后兼容：现有 4 个环境变量继续可用（读取时给弃用提示） |
| C1 | 不修改上游 `script/`、`rosetta/`、`recipe/` |

---

## 3. 锚点模型

~~~
PROJECT_ROOT                  仓库根 = 含 pyproject.toml 且含 t2i/ 的目录
├── t2i/    = T2I_ROOT       工具链与产物（版本库追踪）
│   ├── eval/  workflows/  ComfyUI-C2C/
│   └── results/  report/  exp_v2/  docs/
└── runtime/ = RUNTIME_ROOT  权重 + venv（.gitignore 排除）
    ├── models/  venv/
    └── script/  rosetta/    → junction 回仓库根
~~~

**不变量 I1**：`RUNTIME_ROOT` 是 `PROJECT_ROOT` 的直接子目录。
由此可推出 `PROJECT_ROOT = dirname(RUNTIME_ROOT)`、`T2I_ROOT = PROJECT_ROOT/t2i`。
这条不变量让"只知道 runtime 位置"也能推出另外两个锚点 —— 正是节点包场景（G3）所需。

---

## 4. 解析算法

### 4.1 探测优先级（自上而下，命中即止）

1. **显式环境变量** `C2C_PROJECT_ROOT`（指向仓库根）
2. **从 `Path(__file__).resolve().parent` 上溯**：找同时含 `pyproject.toml` 与 `t2i/` 的祖先目录
3. **从 `Path.cwd().resolve()` 上溯**：同上
4. 失败 → 抛 RuntimeError，报错文本给出可执行修复方案

> **必须用 `.resolve()`**：它等价于 `os.path.realpath`，会穿透 junction 与 8.3 短名。直接用 `__file__` 字面量会在 junction 场景下退到 ComfyUI 安装目录。

### 4.2 RUNTIME_ROOT 的探测

1. `C2C_RUNTIME` env
2. `C2C_ROOT` env（兼容旧名）
3. `PROJECT_ROOT/runtime`

### 4.3 G3 junction 穿透：实测结论

设计初稿曾假设"Python 不解析 junction，节点包无法用 `__file__` 定位仓库，必须依赖环境变量"。
**实测推翻了这个假设**：`Path(__file__).resolve()` 走 `os.path.realpath`，**会穿透 junction**。

| 场景 | `__file__` 字面量 | `Path(__file__).resolve()` | 锚点探测结果 |
|---|---|---|---|
| 仓库内脚本（t2i/eval/） | 仓库内 | 仓库内 | ✅ 命中仓库根 |
| 节点包经 `custom_nodes/ComfyUI-C2C`（junction） | ComfyUI 安装目录 | **仓库内** | ✅ 命中仓库根 |
| 仓库外脚本 + 无环境变量 | 仓库外 | 仓库外 | ✅ 正确失败（不猜） |
| 任意目录 + `C2C_PROJECT_ROOT` | — | — | ✅ 直接采用显式值 |

结论：
- **仓库根定位不依赖环境变量**，节点包也能自解析 → 原设计稿的"必须设 C2C_ROOT"约束**取消**。
- `C2C_ROOT` / `C2C_RUNTIME` 仍然保留，但语义收窄为**运行时目录的覆盖**（runtime 可能放在仓库外的共享缓存盘）。
- 节点包仍建议设置 `C2C_ROOT`：当 `runtime/` 不在仓库内时（共享缓存），只有 env 能指出它。

### 4.4 失败策略（G4）

`runtime/` 不在版本库。新克隆后运行脚本时，`paths.py` 检测到 `RUNTIME_ROOT/models` 缺失应抛出：

~~~
Runtime assets missing under <path>.
Populate it with:
  python t2i/download_models.py
  uv venv runtime/venv --python 3.10
  uv pip install --python runtime/venv/Scripts/python.exe <deps>
~~~

---

## 5. 存储期规范（相对基准表）

**总则**：被版本库追踪的文本文件里不出现盘符绝对路径。相对基准统一为 `T2I_ROOT`。

| 数据 | 相对基准 | 示例 |
|---|---|---|
| `results/metrics/manifest.csv` 的 image_path | T2I_ROOT | `exp_v2/A_moss_p01_s42/raw_00001_.png` |
| `results/metrics/image_metrics.csv` 的 image_path | T2I_ROOT | 同上 |
| `results/batch_list.txt` | T2I_ROOT | `workflows/runs_v2/A_moss_p01_s42_moss.json` |
| `results/prompts_generated/*.json` | T2I_ROOT | 相对 prompt 文件引用 |
| `workflows/runs_v2/*.json` 的 filename_prefix | **不适用** | 相对 ComfyUI 输出目录，非本项目 |
| `docs/*.md` 中的项目内路径 | PROJECT_ROOT | 标注为"相对仓库根" |

**解析侧统一入口**：`paths.resolve(p)` 以 `T2I_ROOT` 为基准绝对化；已是绝对路径则原样返回。
这样"存相对、用绝对"两种形态都能喂给同一个函数。

---

## 6. 环境变量统一（兼容层）

| 旧名 | 新名（首选） | 兼容策略 |
|---|---|---|
| `PLAYGROUND` | `C2C_PROJECT_ROOT` | 仍读取，打弃用提示 |
| `COMFY_OUT` | `C2C_EXP_OUT` | 仍读取，打弃用提示 |
| `EXP_OUT_DIR` | `C2C_EXP_OUT` | 仍读取，打弃用提示 |
| `C2C_ROOT` | `C2C_RUNTIME` | 仍读取（优先级更高的兼容名） |

弃用提示只发一次：`DeprecationWarning: PLAYGROUND is deprecated, use C2C_PROJECT_ROOT`。

---

## 7. 单一事实来源：t2i/paths.py

~~~python
"""Canonical path resolution for the C2C-on-T2I toolchain.

Anchors (G1):
    PROJECT_ROOT  repo root (holds pyproject.toml + t2i/)
    T2I_ROOT      t2i/      -- toolchain + artifacts (tracked)
    RUNTIME_ROOT  runtime/  -- weights + venv (git-ignored)

Invariant:
    I1  RUNTIME_ROOT is a direct child of PROJECT_ROOT
        => PROJECT_ROOT = dirname(RUNTIME_ROOT), T2I_ROOT = PROJECT_ROOT / "t2i"
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

__all__ = [
    "PROJECT_ROOT", "T2I_ROOT", "RUNTIME_ROOT",
    "RESULTS_DIR", "METRICS_DIR", "BLIND_DIR", "FIGS_DIR",
    "EXP_OUT", "DOCS_DIR", "WORKFLOWS_DIR", "PROMPTS_FILE",
    "MODELS_DIR", "VENV_PY", "BRIDGE_PY",
    "resolve", "relative", "require_runtime",
]


def _find_project_root(start: Path) -> Path | None:
    for cand in [start, *start.parents]:
        if (cand / "pyproject.toml").exists() and (cand / "t2i").is_dir():
            return cand
    return None


def _detect_project_root() -> Path:
    env = os.environ.get("C2C_PROJECT_ROOT")
    if env:
        p = Path(env).resolve()
        if (p / "t2i").is_dir():
            return p
        raise RuntimeError("C2C_PROJECT_ROOT={} has no t2i/ subdirectory".format(env))

    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        found = _find_project_root(start)
        if found:
            return found

    raise RuntimeError(
        "Cannot locate the C2C-on-T2I project root.\n"
        "Fix by one of:\n"
        "  - set C2C_PROJECT_ROOT to the repository root\n"
        "  - run the script from inside the repository\n"
        "  - keep t2i/paths.py next to a pyproject.toml at the repo root\n"
    )


PROJECT_ROOT: Path = _detect_project_root()
T2I_ROOT: Path = PROJECT_ROOT / "t2i"

# I1: runtime/ is a direct child of the project root.
_runtime_env = os.environ.get("C2C_RUNTIME") or os.environ.get("C2C_ROOT")
if _runtime_env:
    RUNTIME_ROOT: Path = Path(_runtime_env).resolve()
else:
    RUNTIME_ROOT = PROJECT_ROOT / "runtime"

RESULTS_DIR   = T2I_ROOT / "results"
METRICS_DIR   = RESULTS_DIR / "metrics"
BLIND_DIR     = RESULTS_DIR / "blind"
FIGS_DIR      = T2I_ROOT / "report" / "figures"
EXP_OUT       = T2I_ROOT / "exp_v2"
DOCS_DIR      = T2I_ROOT / "docs"
WORKFLOWS_DIR = T2I_ROOT / "workflows"
PROMPTS_FILE  = T2I_ROOT / "prompts_v2.json"

MODELS_DIR    = RUNTIME_ROOT / "models"
VENV_PY       = RUNTIME_ROOT / "venv" / "Scripts" / "python.exe"
BRIDGE_PY     = RUNTIME_ROOT / "c2c_bridge.py"


def resolve(p, base: Path = T2I_ROOT) -> Path:
    """Absolute path -> Path. Relative inputs resolve against 'base'."""
    p = Path(p)
    return p if p.is_absolute() else (base / p)


def relative(p, base: Path = T2I_ROOT) -> str:
    """Absolute path -> POSIX-style path relative to 'base' (storage form)."""
    return Path(p).resolve().relative_to(base.resolve()).as_posix()


def require_runtime() -> None:
    """Fail loudly with actionable steps when runtime assets are absent (G4)."""
    missing = [d for d in (MODELS_DIR, VENV_PY.parent) if not d.exists()]
    if missing:
        raise RuntimeError(
            "Runtime assets missing under {}\n".format(RUNTIME_ROOT)
            + "Populate it with:\n"
            + "  python t2i/download_models.py\n"
            + "  uv venv runtime/venv --python 3.10\n"
            + "  uv pip install --python runtime/venv/Scripts/python.exe <deps>\n"
        )
~~~

**导入方式**（调用方统一 2 行 bootstrap）：

~~~python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import T2I_ROOT, RESULTS_DIR, METRICS_DIR
~~~

---

## 8. 重映射工具：t2i/eval/relocate_paths.py

一个工具支持两个方向，用于**存量数据**重写（代码侧改用 paths.py 后，数据侧仍需批量迁移）：

~~~
usage: relocate_paths.py {relativize,absolutize,check} PATH...
  relativize   absolute -> relative to T2I_ROOT (storage form)
  absolutize   relative -> absolute (legacy-tool compatibility)
  check        report only, no modification
options:
  --base {t2i,project,runtime}   relative base, default t2i
  --dry-run                     print a diff preview
  --ext .csv,.json,.txt         restrict file types
~~~

适用对象：`batch_list.txt`、`results/metrics/*.csv`、`results/prompts_generated/*.json`。

---

## 9. 校验器：t2i/eval/check_paths.py

可本地运行、可接 CI，四条断言：

1. **无绝对路径泄漏**：扫描 `git ls-files` 的文本文件，断言无盘符路径（白名单：`docs/HANDOFF.md` 的 ComfyUI 安装路径）
2. **相对路径可解析**：`manifest.csv` / `image_metrics.csv` 的 image_path 逐条 resolve()，断言存在
3. **基准一致**：`batch_list.txt` 每行相对 T2I_ROOT 可解析
4. **锚点自洽**：三个锚点满足不变量 I1；`resolve` 与 `relative` 互逆

---

## 10. 迁移步骤

每步可独立回滚，前一步不改变行为。

| 步 | 内容 | 验收 |
|---|---|---|
| **M1** | 新增 `t2i/paths.py`（只新增，不改调用方） | `import paths` 成功，锚点与现状一致 |
| **M2** | 新增 `relocate_paths.py` 与 `check_paths.py`，跑基线报告 | 报告复现 §1.4 的 3 处泄漏 |
| **M3** | 调用方切到 `paths.py`（bridge、smoke_test、nodes、collect、run_eval、make_figs、make_blind_html、analyze_votes、analyze_robust、stats、sheet_to_votes、build_workflow、run_batch） | 输出逐字节不变（同输入重跑比对） |
| **M4** | 数据重映射：`batch_list.txt` 相对化；legacy 脚本去硬编码；`run_batch.py` 支持相对列表 | `check_paths.py` 全绿 |
| **M5** | 文档：HANDOFF 文件地图与命令块改为相对表述；新增"路径约定"小节 | 人工复核 |

---

## 11. 风险与不做的事

| 风险 | 缓解 |
|---|---|
| 节点包在 junction 场景下的锚点定位 | **已实测 `Path.resolve()` 可穿透**，不依赖环境变量；仅当 `runtime/` 迁到仓库外时才需要 `C2C_RUNTIME`（改动节点包后须重启 ComfyUI） |
| 切换锚点后脚本输出路径变化，破坏既有工作流 | M3 以"输出逐字节不变"为验收门槛 |
| `runtime/` 不在版本库，新克隆缺权重 | `paths.require_runtime()` + 可执行报错 |
| 上游代码若引入本地绝对路径 | `check_paths.py` 断言 1 拦截 |
| **不做** | 不改上游 script/、rosetta/；不把 exp_v2（1.1 GB）纳入版本库；不重写已推送的历史 |
