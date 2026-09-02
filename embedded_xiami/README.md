# Embedded Xiami Bot

This directory is a toolbox-local copy of the Xiami bot core for the Dark Workbench QQ bot page.

Copied from:

- `D:\AI程序编辑\QQ机器人\xiami_core`
- `D:\AI程序编辑\QQ机器人\xiami_plugins`

Intentionally not copied:

- `runtime`
- `logs`
- `downloads`
- QR/login state
- PySide6 desktop UI

The toolbox page should use this copy through PySide2/Python 3.8 compatible adapters. Do not import or launch the original PySide6 main window inside the toolbox process.
