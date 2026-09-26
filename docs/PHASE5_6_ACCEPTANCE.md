# Phase 5 Drawing 对齐与 Phase 6 Final Hardening 验收

日期：2026-09-26。基于 `codex/sqlite-domain-reset` 的未提交工作区，起点 HEAD 为 `6b7d8f97079a4b32a81bd3fe6a8f96af5de4ad4a`。本轮只交付本地代码和证据，没有提交或推送。

## 交付与边界

- Drawing 保持独立应用和纸面 SVG/PDF 业务。共享的 `ui-tokens.css` 只统一控件颜色、字体、间距和焦点；全高 Drawing shell 将 Edit、Add annotation、Insert、Document 分组，Back、Save、Export PDF、Cancel job 保持直接可达。左树、纸面、右属性和 checks 各自滚动；窄屏侧栏互斥覆盖。
- 移除了 Drawing 旧的 `570px` 固定工作区高度及过时的 `1100/760px` 断点。修正菜单和原生 dialog 的焦点归还；Escape 关闭菜单时不再取消纸面 anchor picking 或额外请求 render。
- Studio Inspector 分组和折叠状态、构建 busy 锁、分隔条 ARIA、菜单焦点、原生 dialog 优先级、响应式布局、Reset layout 和 `pmc:studio-layout:v1` 校验继续沿用并完成回归。本轮没有 v2 storage 迁移。
- Viewer 补齐选中对象的局部 U/V/IN 坐标标识；Drawing 的 SVG 编辑视图补齐透明内部命中区域，便于从视图空白处拖动。这两项仅属于屏幕交互，不改变工程数据或导出 PDF。
- Manufacturing / Export 为可用文件设置下载文件名，避免 `manufacturing.json` 在浏览器中直接打开；禁用条件继续由现有 dirty、stale、external-change、busy 和 build 状态决定。
- 自动生成的安装孔在 Tree / Inspector 使用 `Mounting Hole N` 展示名称；复制安装孔继续使用安装孔 ID 家族。稳定 ID 仍显示在 Advanced 信息中，不修改保存 schema。
- 未改后端 API、工程 schema、几何、路由、校验规则、Drawing source/render/PDF 实现。精确 wall/clearance 尺寸线仍是延期项，需要后端同源测量端点。

## 已运行的检查

| 检查 | 结果 |
|---|---|
| `npm run build` | 通过，Studio 与 Drawing 均构建；保留既有运行时字体 URL 和主包体积提示。 |
| Node 前端回归 | 29 passed，0 failed。命令见 [Phase 4 验收记录](PHASE4_ACCEPTANCE.md)。 |
| `.venv` Python Store/API、项目、Drawing、预览和工程视图回归 | 66 passed，23 warnings；未改后端实现。 |
| `node scripts/check-viewer-lifecycle.mjs` | 通过：透视/正交真实拖动、同步本地 frame、transient reset。 |
| `node scripts/check-phase4-browser.mjs` | 通过：11 张截图、0 个项目写入请求。 |
| `node scripts/check-phase5-6-browser.mjs` | 通过：15 个非 render POST、3 个 Drawing 只读 render POST，全部发往隔离服务 `127.0.0.1:8766`；0 page error、0 越界 API 请求。 |
| `git diff --check` | 通过，仅 Git 的 LF/CRLF 转换提示。 |

写入型浏览器验收使用 [隔离服务启动器](../scripts/phase4-isolated-server.py)，只在 `output/phase4-isolated/` 内建立 Projects、Output、Drawings、Templates 和 SQLite 副本。服务拒绝 8765 端口；浏览器路由阻断非 8766 的 API 请求。测试项目为 fixture 创建，不使用真实用户项目、AI 分析或真实不可变构建。隔离 fixture 的精确构建结果是 **FAIL**；这不等于生产项目状态，也没有被改成 PASS。

浏览器实际验证了：A→B 切项目清除 isolation/clipping 并保留 session projection，导航不产生 dirty；Inspector 折叠后重绘仍保留状态；Drawing 创建完成后在 1366×768 和 900×800 的纸面与 checks；窄屏侧栏互斥且不修改 edit；菜单 Escape 不触发 render；原生 dialog Escape 及焦点归还；Note 的 Undo/Redo、Save、Reload 后仍存在；草稿 PDF 导出；Validate 运行时菜单、保存、构建及 Add Cavity 被锁定，结束后恢复且草稿不 dirty。生成的隔离 PDF 为 `%PDF-1.3`，161461 字节，**草稿图纸**，不是发行版。

已目视检查 [Drawing 1366×768](../output/playwright/phase5-6/drawing-created-1366x768.png) 与 [Drawing 900×800](../output/playwright/phase5-6/drawing-created-900x800.png)：纸张位于 board 内，顶栏操作和检查区可见，页面无整页滚动。机器记录为 [acceptance.json](../output/playwright/phase5-6/acceptance.json)，草稿产物为 [drawing-draft.pdf](../output/playwright/phase5-6/drawing-draft.pdf)。这些文件位于忽略的 `output/`，不属于 Git 交付。

## 追加隔离浏览器验收

后续在同一个隔离服务上补跑了两个写入型脚本。Studio 的 [机器结果](../output/playwright/studio-remaining/acceptance.json)为通过、0 page error、0 越界 API 请求、0 个意外 exact build 请求；依次下载六种当前 PASS 构建输出：`production.step`、`engineering.step`、`design.json`、`validation.md`、`drill-chart.csv`、`manufacturing.json`。浏览器实际验证了 dirty 导出门禁与 Reload 确认、Mounting Hole / 一次性 External Port / Engraving / Block Machining / Engineering Library Cavity 的创建入口、Duplicate / Suppress / Restore / Delete、干净草稿的外部自动重载，以及脏草稿遇到 revision 409 时保留本地修改。[导出画面](../output/playwright/studio-remaining/studio-pass-exports-1366x768.png)、[编辑画面](../output/playwright/studio-remaining/studio-feature-draft-1366x768.png)及[冲突画面](../output/playwright/studio-remaining/studio-revision-conflict-1366x768.png)均已目视检查。

Drawing 的 [机器结果](../output/playwright/remaining/acceptance.json)为通过、0 page error、0 越界 API 请求。基于单独的当前 PASS fixture，实际完成了创建、发行不可变 PDF、创建 B 修订、从视图内部拖动、Undo、Save、尺寸拾取取消与添加、Insert 菜单、历史 PDF、源更新取消与应用、复制图纸，以及双窗口 optimistic revision 409 且本地未保存编辑保留。发行 PDF 为两页，可解析，位于 [drawing-issued.pdf](../output/playwright/remaining/drawing-issued.pdf)；历史保存 PDF 为 [drawing-saved-history.pdf](../output/playwright/remaining/drawing-saved-history.pdf)。[1366×768](../output/playwright/remaining/drawing-pass-1366x768.png)、[1920×1080](../output/playwright/remaining/drawing-pass-1920x1080.png)、[1100×800](../output/playwright/remaining/drawing-pass-1100x800.png)、[900×800](../output/playwright/remaining/drawing-pass-900x800.png)及[源更新后的窄屏](../output/playwright/remaining/drawing-updated-900x800.png)已目视检查，纸面及主要控件均位于窗口内。

以上 PDF、截图与机器结果位于 Git 忽略的 `output/`，属于本机验收证据，不纳入源码提交。验收使用测试 fixture，不触及真实用户项目或付费 AI。没有已提交的像素级视觉基线，因此只声明人工目视检查，不声明自动视觉回归通过。

## 保留的边界与未验证项

- 尚未穷举所有特征类型在两种投影下的真实拖动、clipping 与所有 hit area / label / lazy layer 过期返回的组合，或阻止取消的原生 dialog。代表性的双投影拖动、三轴剖切、隔离、项目 transient reset 和键盘路径已经实际跑过。
- Drawing 的关联尺寸、表格、视图与纸面锚点业务由既有 Python 测试及上述代表性浏览器操作覆盖；浏览器未逐一执行每个命令选项、每种纸面对象或极低高度窗口。
- 没有发起外部付费 AI 分析。精确 minimum-wall / clearance 尺寸线按 [Phase 4 计划](PHASE4_ACCEPTANCE.md)延期：后端尚无同源测量端点，不能以 bounds 或中心连线冒充工程证据。
- 无后端几何、路由、校验源码改动，因此未运行 `python -m manifold prove`。若今后添加权威测量输出，应补跑该证明和对应工程测试。
