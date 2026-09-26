# Studio UI 改版验收记录（Phase 1–3）

日期：2026-09-25。实施基于工作区当前代码（起点 `77400f9`），只改 Studio/Home 前端和使用说明；未改 Drawing 工作区、后端 API、项目 schema、几何、路由或校验规则。

## 实施范围

- 新深色视觉规范、紧凑控件及内联 SVG 图标；Projects 首页、向导和现有弹窗沿用同一视觉样式。
- Studio 全高布局、可调整/折叠侧栏、窄窗口覆盖式侧栏、Viewport HUD、操作状态条和 Validation Results 抽屉。布局偏好只写入浏览器本机 `pmc:studio-layout:v1`，Reset layout 可清除。
- Project/Engineering/Display/Add Feature 菜单，复用原有命令 ID 和事件处理器；Feature Tree 的 Generated Routes 分组、Inspector 分组与状态保持、Manufacturing / Export 折叠区域。
- 校验结果保留来源标识及报告内容。结果行只选择仍存在于当前草稿/提案中的 feature，不将无对应 feature 的旧报告条目误选为 Block。

## 已执行检查

| 检查 | 结果 |
|---|---|
| `npm run build` | 通过；Studio 与 Drawing 两个入口均生成。Vite 仍提示运行时字体 URL 与主 chunk 大小。 |
| 前端队列、流式预览、Library UI、产品回归、路由对齐测试 | 25/25 通过（`node --test --test-isolation=none ...`）。 |
| Store/API 与项目 Python 测试 | 16/16 通过，5 条已有弃用提示。 |
| `node --check`、`git diff --check` | 通过。 |
| 本地服务 `/api/health` | HTTP 200。 |
| `tests/studio-shell.run.js` 真实浏览器脚本 | 通过；7 张截图，0 次项目保存/构建 POST，0 个页面异常。 |

浏览器脚本用五步向导创建**未保存**草稿；检查 Projects 返回草稿、菜单 Escape/方向键与焦点恢复、Library 和五类 Add Feature 入口、Display/网络控制、Inspector 折叠记忆、侧栏鼠标拖动/键盘调整与本地偏好、状态条展开、Validation 抽屉，以及 1366×768、1920×1080、2560×1440、1100×800、900×800。截图位于 `output/playwright/studio-*.png`。已目视检查 Home、1366/1920/2560 工作区、Validation 抽屉和 1100/900 覆盖层截图。

在本地浏览器中还以只读方式打开一个已保存的 STALE 项目，确认生成路由分组、旧构建结果来源提示和 Studio 的 **Drawing** 跳转到独立 Drawing 页面；随后返回 Studio。未保存该项目，也未运行新的构建。

## 尚未逐项执行的人工场景

- 没有在真实项目上执行重命名、复制、归档/恢复、永久删除或制造 revision 冲突；这些操作会改变用户项目。Home 搜索与归档切换已在未保存草稿路径检查。
- 没有通过浏览器提交各类 feature 的最终创建、Duplicate/Suppress/Delete，或显式 Validate 生成新的不可变构建。入口已在浏览器打开；原业务处理器保留，Store/API 测试通过。
- 没有逐个切换六个视图、全部显示层、Smart align、网络可见性及所有 Inspector 字段；已检查 HUD/Display 控件可达、紧凑模式调用原 Viewer 模式处理器。
- 没有从浏览器发起付费 AI 分析、模拟外部冲突/服务故障或下载六类真实构建产物。AI 业务路径、保存/构建门禁与下载 URL 未改动。
- 本轮未触及几何/路由/校验实现，因此未重跑 `python -m manifold prove`；原有工程证明仍需在这些实现发生变化时执行。

这些未执行项不应被理解为已通过的端到端验收。本段记录的是原阶段仅交付本地代码、UI 验收脚本和截图时的状态；后续提交及复验以 [Phase 5/6 验收记录](PHASE5_6_ACCEPTANCE.md)和 Git 历史为准。没有部署应用服务。
