# AGENTS.md

## 项目概况

这是一个 Windows Python/Qt 桌面程序。主入口是 `工具箱_qt.py`，新版壳层在 `dark_workbench_shell.py`，当前默认运行目标是 Dark Workbench UI。项目主要运行时仍以 PySide2 / Python 3.8 为准，打包使用 PyInstaller 和项目根目录的 `虾米工具箱.spec`。

## 当前追求目标

持续完善虾米工具箱新版 Dark Workbench UI：优先修复乱码与视觉断层，再按小批次优化导航、布局密度、主次操作层级和高频功能页体验；同时补齐遗漏入口、避免已恢复页面回归，并控制重构范围不要外溢到暂不改版的页面。

执行这个目标时，每批只处理一个可验证页面或一类共性问题。优先使用已有 smoke 参数和截图产物证明结果，不用主观判断替代当前渲染证据。

持续任务中补充轻量视觉回归能力，当前纳入以下调研结论：

- `computer-use` 对本目标有用，但定位为阶段性真实桌面巡检：每完成数个 UI 批次或打包前，用它启动 Dark Workbench，按旧主界面入口对照点击导航、高频页面、弹窗、滚动和焦点状态，补充标准 smoke 截图无法覆盖的桌面交互证据。
- 当前本机 Codex 插件缓存未发现专用 `visual diff` / 截图对比插件；不要等待插件市场能力，先用项目脚本和本地开源工具补齐。
- 轻量截图对比优先评估 `pytest-image-snapshot` 或 `reg-cli`，目标是比较 `artifacts\smoke-*.png` 与基线目录并输出差异图或 HTML 报告；先作为辅助证据，不阻塞常规 smoke。
- 若需要 Python 内嵌、感知相似度或更细粒度像素分析，再评估 `PostHog/pixelhog`。
- 第三方 `SuperBased` Codex 插件只作为后续候选调研项，不默认引入当前项目流程。
- 暂不引入 Visual Regression Tracker、reg-suit、BackstopJS 等偏重平台或 Web 前端的方案，除非后续明确进入 CI/团队化视觉验收阶段。

UI 设计决策优先参考 `DarkWorkbench_DESIGN.md`：按其中的页面模板、token/metrics 落点、组件状态表和小批次验收清单执行；该文档吸收 `awesome-design-md` 的规范结构，但不直接套用外部网站品牌视觉。

当前已确认的 Dark Workbench 入口补齐状态：

- 旧主界面仍存在但新版壳层曾遗漏的真实功能页已恢复并挂载：`刷怪设置`、`存销设置`、`回收生成`、`变量查询`、`封挂编码/编码转换`、`免费微端`。
- 每恢复一个入口，都要同步补齐对应导航项、真实页面 mount、`--dark-workbench-page` 显式打开能力，以及标准 smoke 截图产物；没有现成 smoke 数据时先证明真实页面可打开，不伪造完整业务验证。
- `脚本注入` 已作为遗漏入口恢复到 Dark Workbench；后续导航、布局或壳层重构不得再次移除该标签页，相关 smoke 也要持续保留。
- 每批开始前先复核旧主界面入口与当前 Dark Workbench 导航，继续确认是否还有遗漏页面；一旦发现新增遗漏，先写入本目标再恢复，不要把“是否遗漏其他页面”留到最后才处理。
- 2026-06-17 已完成一轮旧主界面懒加载路由对照审查；按页面别名归并后，当前 Dark Workbench 导航、真实页面 mount、`--dark-workbench-page` 显式打开能力和标准 smoke 截图矩阵已覆盖这些已知入口。
- 后续每批入口或导航改动前后都要继续对照旧主界面入口，防止已恢复页面回归；发现新增遗漏时先写入本目标，再按小批次恢复。
- `账号登录` 是否恢复为独立页面暂定为待确认；当前 Dark Workbench 使用左下角授权状态块，不默认按遗漏页面处理。
- `网站管理` 页面后续会功能大改，当前不要继续做额外 UI 打磨，只保留必要启动、挂载和 smoke 验证。

## 一键命令

根目录入口：

```bat
build.cmd
test.cmd
run.cmd
package.cmd
```

PowerShell 入口：

```powershell
.\scripts\build.ps1
.\scripts\test.ps1
.\scripts\run.ps1
```

快速语法/构建前校验：

```powershell
.\scripts\build.ps1 -ValidateOnly
```

干净 PyInstaller 构建：

```powershell
.\scripts\build.ps1 -Clean
```

发布打包沿用现有发布流程：

```powershell
.\scripts\package.ps1
```

根目录也提供等价入口：

```bat
package.cmd
```

## 验证规则

- 修改 `工具箱_qt.py`、`dark_workbench_shell.py`、启动逻辑或脚本后，至少运行 `.\scripts\build.ps1 -ValidateOnly`。
- UI 布局或样式改动后运行 `.\scripts\test.ps1`。该脚本会执行语法检查、Dark Workbench JSON smoke，并生成关键页面截图到 `artifacts\`。
- 后续接入截图对比时，按当前追求目标中的轻量视觉回归方案推进；先作为辅助证据，不阻塞常规 smoke，稳定后再决定是否纳入强制验证。
- `computer-use` 用于阶段性真实桌面巡检，补充标准 smoke 截图无法覆盖的桌面交互证据。
- 人工检查运行 `.\scripts\run.ps1`。需要透传参数时直接追加，例如：

```powershell
.\scripts\run.ps1 --dark-workbench-page db
```

## Python 环境

脚本按顺序查找 Python：

1. `.\.venv-py38-pyside2\Scripts\python.exe`
2. `..\.venv38\Scripts\python.exe`
3. `C:\Python38\python.exe`
4. `.\.venv-pyside6\Scripts\python.exe`
5. PATH 中的 `python`

不要在未确认兼容性的情况下把项目默认运行时切到 Python 3.14。

## 工作边界

- 修改前先运行 `git status --short --branch`，注意本目录可能处在上级 Git 仓库中。
- 优先修改源文件和 `scripts\` 下的一键脚本。
- 不要手工编辑 `build\`、`dist\`、`__pycache__\`、`__zip_stage__\`、`source_backups\`、`legacy_recovery_archive\` 等生成或归档目录。
- smoke 目录如 `smoke_db_records\`、`smoke_map_settings\`、`smoke_drop_rate\` 只用于验证数据，不当作真实用户数据。
- UI 改动要保留截图路径和命令结果，便于后续批次复查。

## 长任务编排

持续 UI 重做不要在一个过大的上下文里盲目推进。当前线程做协调和结果汇总；每一批限定为一个页面、一个布局问题或一个共性样式问题。批次结果应包含：目标、改动文件、验证命令、截图路径、剩余风险和下一步建议。
