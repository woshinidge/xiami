# 虾米工具箱 (Xiami Toolbox)

**版本 1.4.5** | 基于 PySide2 (Qt) 的 Windows 桌面工具箱

> 本项目为 **私有仓库**（Private Repository），仅供授权使用。

---

## 概述 (Overview)

虾米工具箱是一个功能丰富的 Windows 桌面应用程序，主要面向游戏服务端管理与数据编辑场景。基于 Python 3.8 + PySide2 构建，支持多种业务模块的统一管理与操作。

### 核心特性

- 🧩 **模块化界面**：采用 Dark Workbench UI 壳层，支持多标签导航与真实页面挂载
- 🗃️ **数据管理**：支持 CDK、数据库、编码、变量查询等多种记录管理
- 💱 **货币兑换**：内置汇率/货币配置管理
- 📊 **爆率查询**：游戏掉落数据查询与同步分析
- 🧞 **NPC 可视化**：NPC 拖拽编辑框架（C# 迁移至 Python）
- 📦 **脚本注入**：脚本模板管理与批量注入
- 🔧 **商店/刷怪/回收设置**：游戏服务端配置管理
- 🌐 **内置网站管理**：基于模板的传奇官网生成与发布
- ⚡ **C++ 原生扩展**：`native/core_worker` 提供资产解码、压缩、调色板等高性能能力
- 🔌 **嵌入式插件系统**：`embedded_xiami` 提供可扩展的插件架构

### 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.8, C++17 |
| GUI 框架 | PySide2 (Qt 5.x) |
| 打包工具 | PyInstaller |
| 原生扩展 | C++ (native/core_worker) |
| 插件系统 | 嵌入式 Python 插件 (embedded_xiami) |
| 构建工具 | PowerShell + cmd 脚本 |

---

## 项目结构 (Project Structure)

```
xiami-toolbox/
├── 工具箱_qt.py                    # 主程序入口
├── dark_workbench_shell.py         # Dark Workbench UI 壳层
├── toolbox_native_core.py          # 原生核心接口
├── toolbox_core_rpc.py             # 核心 RPC 通信
├── toolbox_capabilities.py         # 能力声明
├── toolbox_update.py               # 更新系统
├── toolbox_security_events.py      # 安全事件
├── visual_spawn_page.py            # 刷怪可视化页面
├── embedded_droprate_template.py   # 爆率模板
├── atomic_target_commit.py         # 目标提交
├── toolbox_backend_tls.py          # TLS 后端
├── toolbox_crash_logging.py        # 崩溃日志
├── toolbox_target_scope.py         # 目标范围
├── toolbox_native_asset_worker.py  # 资产工作器
│
├── build.cmd / run.cmd / test.cmd / package.cmd  # 一键构建脚本
├── 虾米工具箱.spec                   # PyInstaller 打包配置
│
├── native/                         # C++ 原生源码
│   └── core_worker/                # 资产解码器、压缩、调色板
├── embedded_xiami/                 # 插件系统
│   ├── xiami_core/                 # 核心插件模块
│   └── xiami_plugins/              # 插件扩展
├── embedded_npc_visual/            # NPC 可视化编辑模块
├── resources/                      # 资源文件（图标、过滤规则）
├── pyinstaller_hooks/              # PyInstaller 构建钩子
├── third_party/                    # 第三方库（miniz 压缩）
├── tools/                          # 开发工具
└── workflow/                       # 工作流配置
```

---

## 快速开始 (Quick Start)

### 环境要求

- Python 3.8+（推荐 3.8）
- PySide2
- 依赖安装：`pip install -r requirements-npc-visual.txt`

### 运行

```bat
run.cmd
```

或直接：

```bash
python 工具箱_qt.py
```

### 构建

```bat
build.cmd
```

### 打包

```bat
package.cmd
```

---

## 构建说明 (Build Instructions)

| 命令 | 说明 |
|------|------|
| `build.cmd` | 构建验证 |
| `test.cmd` | 运行测试与 smoke 截图 |
| `run.cmd` | 直接运行 |
| `package.cmd` | 生成发布包 |

---

## 许可证 (License)

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

Copyright (c) 2026 washinidge