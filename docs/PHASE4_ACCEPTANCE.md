# Phase 4 导航、工程可视化与 Drawing 视觉对齐验收

日期：2026-09-26。实施起点为 `codex/sqlite-domain-reset` 的 `6b7d8f97079a4b32a81bd3fe6a8f96af5de4ad4a`。以下是 Phase 4 当时的验收记录；后续提交和闭环复验见 [Phase 5/6 验收记录](PHASE5_6_ACCEPTANCE.md)。Phase 4 未修改后端 API、项目 schema、几何、路由、校验规则、Drawing 源或 PDF 生成。

## 实施范围

- Studio Viewer 共用原有六面及非对称 ISO 方向表；同一场景在透视与正交相机间切换，保留视线、目标与目标平面可见高度。`frame()` 统一处理对象集合或显式 bounds，`focus()` 同步使用当前显示上下文，无 owner mesh 时使用参数显示范围，不请求 lazy layer。
- ViewCube 提供六面、ISO 和八个角的键盘可访问入口。Feature/contact isolation、单平面 X/Y/Z clipping、hover、对象级问题参考标记与 Validation 联动共享现有 Viewer 和 selection。精确 owner 几何只在 Isolate/Feature layers 等明确需要时请求。
- 真正切项目清除隔离、剖切、hover、问题标记及延后 Fit；同项目预览/构建更新保留相机，投影保留为页面会话偏好。原生 `<dialog>` 自行处理 Escape，随后才按菜单/交互/隔离/剖切逐层关闭。
- Drawing 使用共享的 UI token，但纸面 SVG/PDF 样式与工程源保持独立。全高布局、响应式侧栏、分组命令、可折叠 checks；首次打开或主动 Fit sheet 在错误检查区展开后按可用纸面区域适配。
- Studio 布局仍使用 `pmc:studio-layout:v1`，无 v2 迁移；Inspector 分组、重绘后的折叠状态和精确构建 busy 锁已收口。
- 选中可定位特征时，Viewer 显示局部 U/V/IN 坐标标识；它从当前显示位置派生，随拖动预览更新，切换项目时清除。该标识仅用于空间定位，不作为精确测量证据。

问题标记仅是 **Affected feature reference**，不是精确失效点。精确 wall/clearance 尺寸线属于 **DEFERRED / OUT OF SCOPE**：后端尚无同源测量端点，本轮没有用包围盒或网格距离冒充工程证据。

## 已运行的验证

| 检查 | 实际结果 |
|---|---|
| `npm run build` | 通过，Studio 与 Drawing 均构建。保留既有字体运行时 URL 与主 chunk 大小提示。 |
| Node 前端回归：`phase4-visualization`、`preview-queue`、`preview-stream`、`library-ui`、`product-regressions`、`route-alignment` | 29 passed，0 failed。覆盖原方向、投影数学、稳定 ID/来源门禁及预览队列。 |
| `.venv` Python：`test_store_api`、`test_product_projects`、`test_drawing_workspace`、`test_mounting_drawing_source`、`test_v1_engineering_views`、`test_interactive_preview`、`test_validation_details` | 66 passed，23 warnings。后端源码本轮未改。 |
| `node scripts/check-viewer-lifecycle.mjs` | 通过。真实鼠标在透视与正交下各完成连续拖动；验证 hydrated cavity、当前显示上下文、无 owner mesh 的同步 Focus、多目标/network `frame()`、剖切目标拒绝和 transient reset。 |
| `node scripts/check-phase4-browser.mjs` | 通过；11 张实际浏览器截图，0 个项目写入请求、0 page error。验证 v1 布局恢复/Reset、侧栏调整与恢复、Home 返回、15 个导航入口、三轴剖切、Isolate、原生 dialog Escape 焦点、Validation 入口和 Drawing 纸面 Fit。 |
| `git diff --check` | 通过；仅有 Git 的 LF/CRLF 转换提示。 |

浏览器验收在 `127.0.0.1:8766` 的隔离服务上仅允许 GET 与 Drawing 的只读 `POST /render`；后端实现读取文档、计算 SVG 和检查，不保存。其余 POST 均被浏览器路由阻断。截图中的 Drawing 源变更警告来自隔离服务内已保存的测试图纸，不代表真实用户图纸状态。Python 使用既有隔离 fixture。Phase 4 当时未运行 `python -m manifold prove`，因为没有变更 CAD 几何、路由或权威校验实现；闭环阶段的证明结果见 [后续记录](PHASE5_6_ACCEPTANCE.md)。

## 截图与原始记录

原始机器可读结果：[acceptance.json](../output/playwright/phase4/acceptance.json)。已目视检查以下截图，页面无整体横向或纵向溢出，纸张在首次打开及窄屏主动 Fit 后完整位于 board 内。

| 页面 | 截图 |
|---|---|
| Studio | [1366×768](../output/playwright/phase4/studio-1366x768.png)、[1920×1080](../output/playwright/phase4/studio-1920x1080.png)、[2560×1440](../output/playwright/phase4/studio-2560x1440.png)、[1100×800](../output/playwright/phase4/studio-1100x800.png)、[900×800](../output/playwright/phase4/studio-900x800.png) |
| Drawing 首页/空图纸 | [1366×768](../output/playwright/phase4/drawing-1366x768.png)、[1920×1080](../output/playwright/phase4/drawing-1920x1080.png)、[1100×800](../output/playwright/phase4/drawing-1100x800.png)、[900×800](../output/playwright/phase4/drawing-900x800.png) |
| 已保存 Drawing 纸面 | [1366×768](../output/playwright/phase4/drawing-saved-1366x768.png)、[900×800](../output/playwright/phase4/drawing-saved-900x800.png) |

## 首次只读验收时未执行的项目

- 浏览器没有在真实项目上提交 Save、Validate、feature 增删、Import/Export、Drawing 更新/发行或 AI 分析；这些操作会写项目、不可变构建或可能产生费用。已有 Store/API、Drawing 和前端回归通过，但不能把它们称为本轮完整浏览器端到端验收。
- 没有在独立测试服务中覆盖 A→B 切项目、旧 lazy-layer 返回、revision 409、外部磁盘变更和所有六类对象在双投影下的实际拖动；已对 Viewer transient reset 与两种投影的代表性拖动做浏览器测试。
- 剖切三轴和两侧、对象级隔离、问题行点击已检查；所有网格类别的裁切/拾取组合、碰撞网络对、极窄或低高度窗口、阻止取消的 dialog，以及所有 Drawing 命令的浏览器全流程仍需专项矩阵。
- 没有发起远端付费 AI 分析，也没有重新发行 PDF。精确 wall/clearance 尺寸线因后端证据缺失按计划延期。

本节仅记录首次只读验收时的缺口，不能作为最终未测清单。后续在独立 Projects、Output、Drawings、Templates 和 SQLite 副本上完成了项目切换、Studio 特征创建与导出、Drawing 创建/保存/发行/更新/PDF、修订冲突及 Validate busy 锁的写入型浏览器验收；实际覆盖和仍未验证项见 [Phase 5/6 验收记录](PHASE5_6_ACCEPTANCE.md)。正式本地服务仍使用 `127.0.0.1:8765`；隔离服务只使用 `127.0.0.1:8766`。
