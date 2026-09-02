# Xiami Toolbox UI Optimization Brief

Status: approved
Baseline concept: `outputs/ui-assets/xiami-workbench-concept-v1.png`

## Design Read

Windows server operations toolbox. Restrained industrial precision. Product UI.

- Soul: 5/10
- Spectacle: 1/10
- Density: 9/10
- Primary direction: light cool-gray workbench with restrained Xiami orange

## Scope

Keep the current Python 3.8, PySide2, business logic, routes, data formats,
packaging flow, and Windows Server 2012 R2 compatibility behavior.

Optimize only:

- information hierarchy and local page layout;
- QSS tokens and component roles;
- control density, spacing, and interaction states;
- a limited set of brand assets;
- high-frequency workflows, one batch at a time.

## Protected

- No PySide6/QML, React/Tauri, or business-layer rewrite.
- Do not remove or rename real page keys and restored navigation entries.
- Do not change user data formats or search/generation semantics for visual work.
- Do not add GPU-dependent effects, translucency, or decorative animation.
- Preserve existing dirty worktree changes unless a batch explicitly owns them.

## Layout Principles

- Global project context belongs in the top project bar.
- Navigation is the canonical page directory; page-local duplicate navigation is removed.
- Actions stay close to the object they operate on.
- Tables, editors, results, and previews receive most of the viewport.
- Advanced or low-frequency controls use progressive disclosure.
- Avoid nested cards and page-sized floating cards.
- At 1180x720, primary actions remain visible and main content remains readable.

## Component Principles

- One primary action per page or task group.
- Secondary actions are outlined or muted; destructive actions are explicit.
- Controls use compact native desktop proportions and visible focus states.
- Loading, empty, error, success, and disabled states are designed deliberately.
- Long paths and generated values support tooltip, copy, or a detail surface.

## Image Generation Boundary

`gpt-image-2-api` may produce concept boards, application identity assets,
About/update artwork, and limited empty-state artwork. It must not generate
functional controls, button icons, or final text-heavy page screenshots.

## Batch Contract

Each implementation batch must report target, changed files, verification,
screenshot paths, remaining risk, and one next candidate. Shared source files
must not be edited concurrently.

