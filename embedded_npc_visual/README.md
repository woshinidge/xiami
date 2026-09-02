# Embedded NPC Visual Editor

This package is the toolbox-managed copy of the NPC visual editor from:

`C:\Users\Administrator\Desktop\PAK可视化`

Imported on 2026-07-21. The upstream folder remains unchanged and is not a
runtime or packaging dependency.

Integration-specific changes:

- imports use the `embedded_npc_visual` namespace;
- the version path follows the toolbox project root;
- template/config data is stored below `%LOCALAPPDATA%\XiamiToolbox`;
- Pillow, cryptography, and cffi versions are recorded in
  `requirements-npc-visual.txt`;
- PyInstaller collects the package and its CSV resources from the toolbox tree.
