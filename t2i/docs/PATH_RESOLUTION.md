---
title: 路径相对化重映射设计
status: 设计稿，待实施
scope: C2C-on-T2I/t2i/（工具链与产物）
out-of-scope: 上游 script/、rosetta/、recipe/（均用 HF repo id 或包内相对路径，无本地绝对路径）
---

# 路径相对化重映射设计（PATH_RESOLUTION）

## 0. 沿革：三代 runtime 设计

本文档讨论的 `runtime/` 并不是上游 C2C 的概念。它是三代演进的产物，理清楚才能设计对。

### 0.1 上游 thu-nics/C2C：**没有 runtime 层**

| 维度 | 上游的做法 |
|---|---|
| Python 环境 | **机器级 conda env**：`conda create -n rosetta python=3.10` + `pip install -e .`（`environment.yml` 是作者本机导出的冻结清单，末尾还留着 `prefix: /share/minzihan/miniconda3/envs/rosetta`） |
| 权重 | **直接走 HuggingFace**：`snapshot_download(repo_id="nics-efc/C2C_Fuser")`、`from_pretrained("Qwen/Qwen3-0.6B")` → 落在 HF 缓存，**仓库内没有 models/** |
| fuser checkpoint | 由 `recipe/` + `bash/train/` 训练产出，落在仓库顶层 `checkpoints/`（gitignored） |
| 产物约定 | 仓库顶层 `outputs/ results/ logs/ local/ eval_results/ checkpoints/` —— **全部在仓库内、全部 gitignored** |
| 包结构 | `rosetta/` 是包本体（`pip install -e .` 装的就是它），`script/` 是脚本，`recipe/` 是配方 |

> 上游的核心约定是：**代码进库，产物与缓存留在仓库顶层但不入库，环境与权重交给机器/HF 缓存**。
> 这套约定已经隐含了"仓库内 gitignored 目录"这一思路。

### 0.2 你的 fork 引入的：把权重和环境收进仓库

- `models/`：`download_models.py` 从 HF 拉 fuser 与 Qwen 权重到本地
- `venv/`：uv 管理的 Python 环境（替代 conda）
- `C2C_ROOT` 机制：**一个变量同时指**"c2c_bridge.py 所在目录 + models/ + venv/"
- ComfyUI 节点包通过 `C2C_ROOT` 找到 bridge 与 venv

**但布局有两套、互相矛盾**，这正是"runtime 混淆"的根源：

| 来源 | 说法 | 后果 |
|---|---|---|
| `nodes.py` 默认值 | `C2C_ROOT = C:\Yet\Playground\c2c`（独立 clone，权重与 venv 都在那儿） | 需要单独维护一个 c2c clone |
| `t2i/docs/REPRODUCE.md` | "设 `C2C_ROOT` 指向仓库的 `t2i/` 目录"；而 venv 按 §1 建在**仓库根**（`python -m venv venv`） | 按文档配好，节点包仍找不到 venv（它找 `C2C_ROOT/venv`） |

### 0.3 现在的形态（本设计的目标态）

```
C2C-on-T2I/
├── runtime/          ← 显式的运行时层（gitignored）
│   ├── models/       权重
│   ├── venv/         Python 环境
│   └── script/ rosetta/   junction 回仓库根（避免源码第二份）
└── t2i/              ← 只放工具链与产物
```

### 0.4 对本设计的三条启示

1. **`runtime/` 与上游惯例同构**：上游用"仓库内 gitignored 顶层目录"表达运行时产物，我们用"仓库内 gitignored 顶层目录"表达权重与环境——同一种思路，不算另起炉灶。
2. **环境位置必须只有一处真相**：上游放机器级 conda，你的 fork 放仓库内 venv。两种都可行，但同一次运行里不能同时存在两套（venv 与 conda env、HF 缓存与本地 models/ 择一）。本设计选择：**环境在 runtime/venv，权重在 runtime/models**，其余路径（脚本、产物）全部相对化。
3. **机器特定路径是上游也有的老问题**：`environment.yml` 里的 `prefix: /share/minzihan/...` 正是本次要消灭的那类东西——设计不假设上游是干净的。

### 0.5 一个可选路线（未采纳，供讨论）

沿用上游的 **HF 缓存模式**（`from_pretrained(repo_id)` + `snapshot_download`），则 `runtime/models/` 可整体取消，只保留 `runtime/venv/`：
- 省掉 `download_models.py` 的本地目录管理与 `C2C_ROOT/models` 这一层
- 但权重仍占约 12 GB（只是挪到 HF 缓存），且 fuser 的 24 个 `projector_*.pt` 需要逐文件定位
- 现状是本地 `models/` 已就位且实验已跑通，改造收益不抵风险 → **本设计维持现状**

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

## 12. ComfyUI 节点包：探测本机路径后注入，不改用户目录

### 12.1 问题

节点包（`t2i/ComfyUI-C2C/`）必须出现在 ComfyUI 的节点搜索路径里。ComfyUI 只扫描
`custom_nodes/` 目录，常见做法是往用户安装目录里塞 junction 或副本：

| 旧做法 | 副作用 |
|---|---|
| 在 `custom_nodes/` 建 junction 指向仓库 | **修改用户 ComfyUI 安装目录**；删仓库会让用户的 ComfyUI 出现坏链 |
| 复制节点包到 `custom_nodes/` | 修改用户目录，且产生第二份副本（会与仓库版本分叉） |

### 12.2 机制依据（ComfyUI 0.43.2 实测）

```
folder_paths.py:45   folder_names_and_paths["custom_nodes"] = ([<base>/custom_nodes], set())
utils/extra_config.py load_extra_path_config(): 对 YAML 每个键调用 add_model_folder_path(key, abs_path)
main.py:139-144       自动加载 <ComfyUI>/extra_model_paths.yaml，并接受 --extra-model-paths-config
main.py:200           node_paths = folder_paths.get_folder_paths("custom_nodes")  → 遍历所有注册路径
extra_model_paths.yaml.example:71   custom_nodes 是受支持的键
```

结论：**`custom_nodes` 是一个可从外部配置注册的路径列表**，不必物理存在于安装目录里。

### 12.3 设计

```
C2C-on-T2I/
├── t2i/ComfyUI-C2C/            节点包本体（唯一副本）
└── runtime/                    注入用暂存区（gitignored）
    ├── comfy_nodes/ComfyUI-C2C  → junction 指向 ../../t2i/ComfyUI-C2C
    └── comfy_extra_paths.yaml  → custom_nodes: <runtime/comfy_nodes>
```

启动器 `t2i/scripts/run_comfyui.py`：

1. **探测本机 ComfyUI 绝对路径**（`paths.detect_comfyui()`），顺序：
   `COMFYUI_HOME`/`COMFYUI_PATH`/`COMFYUI_ROOT` 环境变量 →
   comfy-cli 自身的 `config.ini`（`default_workspace`/`recent_workspace`）→
   常见安装位置扫描 → 失败时列出全部探测位置并报错
   解释器取同目录的 `python_embeded/python.exe`
2. **生成注入产物**：`runtime/comfy_nodes/ComfyUI-C2C`（junction，免管理员）+ `runtime/comfy_extra_paths.yaml`
3. **启动**：`<python_embeded>/python.exe <ComfyUI>/main.py --extra-model-paths-config <yaml> --enable-manager`

**用户的 ComfyUI 安装目录全程只读** —— 不建 junction、不复制文件、不写 `extra_model_paths.yaml`。

### 12.4 实测验证

| 项 | 结果 |
|---|---|
| ComfyUI 日志 | `Adding extra search path custom_nodes C:\Yet\C2C-on-T2I\runtime\comfy_nodes` |
| 实时 `/object_info/C2CCompare` | HTTP 200，节点已注册（category `C2C`，输出 `STRING,STRING,STRING`） |
| `custom_nodes\ComfyUI-C2C` | **不存在** |
| `custom_nodes` 中含 `C2C` 的条目 | **0** |
| `<ComfyUI>/extra_model_paths.yaml` | **不存在** |
| 用户目录 10 分钟内改动 | 仅 ComfyUI 自身的 `user/comfyui.log` 与 Manager 缓存 |

### 12.5 与 MCP 的配合

MCP 的 `launch_comfyui` 支持 `extra_args`，因此也可以：
```
launch_comfyui(extra_args=["--extra-model-paths-config", "C:\\Yet\\C2C-on-T2I\\runtime\\comfy_extra_paths.yaml"])
```
前提是先用启动器（或 `paths.write_comfy_extra_paths()`）生成该 YAML。

## 10. 迁移步骤

每步可独立回滚，前一步不改变行为。

| 步 | 内容 | 验收 |
|---|---|---|
| **M1** | 新增 `t2i/paths.py`（只新增，不改调用方） ✅已完成 | `import paths` 成功，锚点与现状一致 |
| **M2** | 新增 `relocate_paths.py` 与 `check_paths.py` ✅已完成 | 报告复现 §1.4 的 3 处泄漏 |
| **M3** | 调用方切到 `paths.py`（bridge、smoke_test、nodes、collect、run_eval、make_figs、make_blind_html、analyze_votes、analyze_robust、stats、sheet_to_votes、build_workflow、run_batch） | 输出逐字节不变（同输入重跑比对） |
| **M4** | 数据重映射：`batch_list.txt` 相对化 ✅已完成（96 条）；legacy 脚本去硬编码；`run_batch.py` 支持相对列表 ✅已完成 | `check_paths.py` 全绿 ✅当前 0 问题 |
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
