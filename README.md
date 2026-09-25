# PMC Manifold Studio

本地优先的参数化液压阀块工程 MVP。Python / CadQuery / OCCT 生成真实 BRep 实体与 STEP；Three.js 显示同一实体离散化的审查模型及明确标记为未验证的编辑预览。手动 CAD 无需登录、数据库或云服务；AI Design 可选连接用户自行配置的多模态 API。

## Windows 启动

本机依赖已安装。双击 `Start-Manifold.cmd`，或在项目目录运行：

```powershell
.\Start-Manifold.ps1
```

打开 <http://127.0.0.1:8765> 后进入 **Projects** 首页，可新建、打开已保存项目或导入项目。默认只监听回环地址。关闭运行服务的终端或按 Ctrl+C 停止。再次启动不会覆盖已有项目。

局域网使用双击 `Start-Manifold-LAN.cmd`，或运行 `.\Start-Manifold.ps1 -LAN`。服务监听 `0.0.0.0:8765`，终端输出本机当前 IP 和主机名入口，无需修改源码中的 IP。若已有本地模式服务，先 Ctrl+C 停止再启动 LAN 模式。在可信局域网中使用；若其他电脑无法连接，在 Windows 防火墙允许专用网络上的入站 TCP 8765，脚本不会自动修改防火墙。同源写入检查仍然生效。停止 LAN 服务后用普通入口恢复本地模式。

另一台 Windows 电脑：安装 **Python 3.11 x64、Node.js 22.12+ 或 24 LTS**，然后运行：

```powershell
.\Start-Manifold.ps1 -Setup
```

首次安装需要网络；安装完成后的建模、校验、网页和导出都在本地运行。脚本使用 `requirements-lock.txt` 和 `package-lock.json` 固定已验证依赖，不修改系统 Python。若 PowerShell 执行策略阻止脚本，使用同目录的 `.cmd` 入口。

直接复制整个目录也可启动：脚本检测失效或迁移的 `.venv`，先保留到 `output/runtime-backups/`，再使用本机 Python 3.11 x64 重建。支持 Python Launcher、uv 管理的 Python 和常见安装目录；uv 存在但未安装 3.11 时先运行 `uv python install 3.11`。Node 从本机查找并用对应 npm 安装依赖，不依赖旧电脑的 npm 启动包装器。可用 `-Python 'C:\路径\python.exe' -Node 'C:\路径\node.exe'` 指定运行时，`-CheckEnvironment` 仅检查、不修改环境。完整首次准备使用 `-Setup`。

本机实际运行结果、最终构建标识和截图见 [VERIFICATION.md](VERIFICATION.md)。

Windows CAD 依赖已固定版本；`manifold/cad.py` 会先加载 CasADi 再加载 CadQuery，规避本机已复现的 NLopt/CasADi DLL 加载顺序导致的退出堆错误。新增 CAD 代码也应从这个模块导入 `cq`，不要绕过它。自动化测试包含真实子进程的正常退出检查。

## 日常设计（新版默认英文界面）

Studio 采用全窗口工作区：Feature Tree 与 Inspector 可拖动宽度或收起，窄窗口改用侧栏抽屉；底部 Validation Results 可展开并调整高度。顶栏的 Project、Engineering 菜单和左侧 **+ Add Feature** 调用原有工作流，Viewport 的 Display 菜单保留图层及逐网可见性。Reset layout 只清除本机界面布局偏好，不修改工程项目。

1. **New Manifold** 五步完成阀块、Metric/Inch 上下文、网络与油口、cavity 选择、放置与接口分配、复核。每个网络独立配置 0–8 个外部油口，每个油口可选择面、规格及 SQLite external-port definition，也可使用 Custom straight bore。Cartridge first 只显示数据库中的明确兼容关系；Cavity first 允许 Cartridge 保持为空。项目只保存稳定 ID 和项目状态，不复制工程主库记录。工程坐标始终为 mm，界面保留完整编辑入口。**Import Project / Export Project** 是 AI 和人工设计的共同入口。项目 JSON 上限 8 MB，图纸二进制仍单独存放在本地 assets。
2. **Schematic** 上传 PDF、PNG 或 JPEG。AI 提供者与模型信息属于可携带的项目来源字段；AI Design 可调用用户配置的服务生成草稿。可选 Codex handoff 收在展开项中，通用 AI 交付格式见 [AI_PROJECT_CONTRACT.md](docs/AI_PROJECT_CONTRACT.md)。
3. **Engineering Review** 管理实际存在的假设、尺寸、选型和连接疑问。Cavity placement 本身不创建 review；工程主库定义在运行时只读。
4. **Engineering Library** 通过后端查询 SQLite 工程主库。Cavity、External port definition 与 Cartridge 是独立概念；项目只保存稳定 ID。影响 CAD 的主数据修改使用新的稳定定义 ID。
5. 元件支持 Duplicate、Replace、Suppress、Delete、换面、位置与网络编辑。六面孔口中心及附近均可开始拖动，悬停高亮、grab / grabbing 光标显示状态；完整安装包络限制边界，默认 1 mm 吸附、Alt 暂停。Undo / Redo 可撤销草稿操作。
6. 三维中直接点击生成的钻孔可检查其网络、尺寸和位置；**Refine in 3D** 固定该回路当前分段，可从可见钻孔整段悬停、选中和拖动。拖动结束后尽可能延长相连正交支路以保留交点，并运行精确草稿检查。**Hydraulic Nets** 区分连接意图和派生钻孔；显式 Optimize 可比较正交轴顺序、入口和偏移路径，最多六个精确候选。Validate 只对报告明确指出可由 reroute 修复的自动 net 产生候选；Cartridge、schematic、review、主库引用和固定几何失败不会触发路线搜索。冻结和手动钻孔保持不变。参数拖动预览仍明确标为未验证；最小壁厚硬规则不变。
7. **Validate** 保存精确 OCCT 实体、验证结果和不可变构建。**Hydraulic nets** 显示按网络分别布尔并集后的液压体；**Machined void** 显示完整加工空腔；**Solid** 显示实体阀块；**Feature layers** 分别检查 cavity、port、液压窗口和闭合区。跨网络接触显示精确碰撞体。编辑先显示明确标识的近似预览，精确结果就绪后更新模型和路线树。预览使用最新快照、合并连续编辑，只显示未验证/未优化的当前候选。失败显示具体原因并保留上一份可用视图。当前 PASS 才开放 STEP；`manufacturing_ready` 独立于几何结果。

运行时工程主库是 `data/pmc_engineering.db`（可用 `PMC_ENGINEERING_DB` 配置）。数据库由开发者/操作员显式从 `PMC_MDTools_Master_Library_2026R2_Merged` 一次性初始化；应用启动不会扫描、导入、重建或修复工程库。缺失或无效数据库会明确失败。初始化与项目转换命令见 [SQLite engineering library](docs/SQLITE_ENGINEERING_LIBRARY.md)。

可执行切削支持圆柱、锥面、显式环槽及旋转后的 footprint 偏移。无法无歧义执行的记录在数据库中标为不可用并说明原因；不猜测缺失尺寸或创建假 geometry variant。演示孔腔仍是演示尺寸。

## AI Design · 原理图生成可编辑三维草稿

从 **AI Design → Provider settings** 自行填写 API 地址、多模态模型名和密钥，没有预设厂商或模型。上传 PDF / PNG / JPEG，输入工程要求，选择配置的模型并点击 **Analyze & create manifold draft**。确认未解决的孔腔选择和液压窗口映射后，系统使用已有库几何、自动布置/布线和精确校验生成草稿；通过 **Open draft in Manifold Studio** 进入普通项目编辑、保存和校验。

当前支持 Chat Completions 图像输入接口。所选图纸和要求会发送给你配置的服务；凭据仅存服务器本机忽略目录，不随项目导出。AI 分析仅使用已配置的真实提供者；未配置时请先完成 Provider settings。模拟提供者和样例原理图仅保留在开发测试目录，不提供正式界面入口。第一版最多 4 个插装阀，采用有限候选搜索；未知接口、兼容性和无法执行的要求保留人工审核。已测试本地模拟服务传输及实际孔腔 CAD 流程，未验证付费远端模型识别准确率。

配置步骤、工程边界与失败恢复见 [AI Design 使用说明](docs/AI_DESIGN_LAYER.md)，验证证据见 [VERIFICATION](VERIFICATION.md)。

真实模型测试可在 Provider settings 控制 reasoning、按任务覆盖、可选 streaming 和契约重试。Max Tokens 无 PMC 上限，留空使用 provider 默认值。失败记录可直接查看耗时、阶段和 token 明细；详细说明见 [Provider diagnostics](docs/PROVIDER_DIAGNOSTICS.md)。

## Drawing Workspace · V2.3

在已保存的 Project 内完成 **Validate → Drawing → Create Drawing**，选择客户图或制造图。两类图纸使用同一个视觉编辑器：精确实体投影、关联尺寸、说明与引出线、视图与基本剖面、表格、PMC 标题栏、模板、撤销重做和矢量 PDF。图纸独立保存于 Project，可重开、检测源变化、预览更新、创建修订和发行不可变 PDF。制造图复用已有 Library / Manifold 数据；新增的普通安装孔是实际非液压切削特征，仍经过实体校验。

操作说明见 [Drawing Workspace](docs/DRAWING_WORKSPACE.md)，实际交付范围、验收证据与参考文件缺口见 [V2.3 验收记录](docs/V23_ACCEPTANCE.md)。图纸状态不会修改工程校验或制造就绪结果。Drawing 及其历史保存在本机，现有 `.pmc.json` 导出仍以 Manifold 数据为范围。

## 和 Codex 协作

当前打开项目的权威记录为 **`projects/saved/<id>.json`**，包含项目状态、工程主库 ID、更新时间、归档标记与构建指针。**Save Project** 保存未通过校验的工作进度；**Validate** 保存并构建。Projects 可搜索、重命名、复制、归档和恢复项目。Delete permanently 要求输入完整项目名，删除该项目记录及修订历史；工程主库、assets 与不可变构建保留。每次启动先展示项目库，不自动打开 demo。项目不嵌入完整 cavity 或 Cartridge 主数据；自动钻孔保存在构建的 resolved_design.json。可以直接告诉 Codex：

- “把 CV2 沿 X 移动 15 mm，重建并检查连接。”
- “把 RV1 改到前面，并调整相关钻孔，保留 7 mm 最小壁厚。”
- “减少 P 油路的堵头，给出通过检查的方案。”

Codex 应使用对应项目 ID 和读取到的 revision。构建已保存项目可运行（把 ID 替换为实际值）：

```powershell
.\.venv\Scripts\python.exe -m manifold build --project-id <project-id>
```

网页每 5 秒检查磁盘设计和构建版本；无草稿时自动更新，有草稿时保留它并提示冲突。保存请求必须携带读取时的 SHA-256，磁盘已变化则返回 409。所有 CLI/API 构建使用同一文件锁；构建期间检测到直接文件修改时放弃提交。命名项目历史保存在 `projects/saved/history/<id>/`，构建输出先写入独立目录，成功后原子更新该项目的指针。旧开发流程的历史仍在 `projects/.history/`。直接编辑 JSON 时建议一次性原子替换文件；CLI 不会为手工编辑之前的内容自动建备份。

## 坐标与连接

单位统一 **mm**；原点在阀块左前底角，X=长度，Y=宽度，Z=高度。

| 面 | U | V | 进刀方向 |
|---|---|---|---|
| left / right | Y | Z | +X / −X |
| front / back | X | Z | +Y / −Y |
| bottom / top | X | Y | +Z / −Z |

`depth` 是圆柱部分深度；118° 钻尖的额外深度由几何引擎计算并参与壁厚检查。180° 表示平底加工。钻孔默认垂直进刀；可选全局单位方向向量支持从六个外表面进入的直线斜孔，入口余弦须不小于 0.25。精确切削仅在声明入口平面裁剪，其他面穿出仍失败。曲线通道、完整夹具和刀具执行尚不支持。

- `cavity`：使用 `definition` 引用库定义，各轴向液压窗口分别通过 `circuits` 指定油路，例如 `CV1:upper` 和 `CV1:lower`。
- `port` / `drilling`：使用独立 `circuit` 字段。颜色由工程 ID 决定，永不通过颜色推断油路。
- `connects_to`：声明**直接几何连接**，如 `G-P` 的 `P, CV1:upper, RV1:upper`。传递连通性由测得的连接图计算。
- 所有实际接触都必须有授权：手动钻孔使用 connects_to；自动钻孔仅对其所属 net 的明确接口及同网派生钻孔生成连接声明。其他接触仍报错。零体积相切不视为通油。
- 堵头占据从入口开始的 `plug_length`，该体积从流体节点中移除；其他切削不得进入堵头啮合区。
- 每个无堵头钻孔必须有同面、同轴、同油路且尺寸足够的外部油口封闭入口。

## 插装孔库与工程边界

开发夹具中保留三个明确标记 **demo_only** 的示例：双区阶梯孔、紧凑双区孔、单区服务孔。它们由真实圆柱切削体构成，但**不是 SUN / HydraForce 的厂家孔腔**。

SQLite 工程定义保存阶梯切削尺寸、液压窗口、安装工具空间、边界和螺纹注记。新增或修改真实定义时必须形成新的稳定 ID，并核对全部工程值。当前内核支持显式圆柱阶梯、锥面/锥底、环状切削体，以及带局部偏移和旋转的 footprint 切削。完整螺纹牙型和尚未映射的特殊退刀槽不自动生成；数据库中存在记录并不代表所有加工细节都已执行，也不能把示例定义宣称为厂家精确实现。

**加工空腔与装阀后的油路不同**：真实未装阀孔腔是连续切削体，液压校验按 cavity interface 窗口建图。同一孔腔的不同窗口不会自动串联；窗口外的孔壁、密封和螺纹区域禁止其他钻孔侵入。首版不模拟阀位及阀内流动。Cavity、Cartridge 和 external-port definition 是独立概念；只有显式 `cartridge_cavities` 关系才能声明兼容，单个居中窗口本身不构成外部油口资格。

PASS 仅代表当前规则范围通过，**不是制造放行或承压认证**。材料为工程元数据；压力、疲劳、流量分配、压损、热、污染、完整刀具/夹具干涉、螺纹强度及密封性能尚未计算；新版提供有明确假设的最小孔径流速筛查。外部油口可引用已有真实加工定义，使用其阶梯、锥面、环槽和偏移切削；也可使用尺寸可配置的 Custom straight bore。完整加工切削体用于减料、壁厚、碰撞和 STEP；液压连接与通油开口仅使用源定义的窗口。浅层螺纹、密封和锪面不能因实体重叠而自动连通。未提供的标准尺寸不推定，螺纹牙型、接头安装密封和承压能力不因选择一个规格而得到认证。外部工具干涉使用声明的圆柱包络及有来源的安装边界；未提供的阀体高度、夹具和工具外形不推定。

## 校验与复现

```powershell
# 几何检查，FAIL 时退出码为 1
.\.venv\Scripts\python.exe -m manifold validate

# 故意加入 P/A 串油，再生成修正版；不改变工作项目
.\.venv\Scripts\python.exe -m manifold prove

# 测试真实几何、错误案例、文件提交和本地接口
.\.venv\Scripts\python.exe -m pytest -q --junitxml=output/tests.xml

# 单独构建其他项目；输出必须是新目录
.\.venv\Scripts\python.exe -m manifold build --project projects/demo.json --out output/manual-build
```

几何校验使用 OCCT 布尔交集、实体距离、精确轴向切削边界、图遍历和 BRep 有效性；不使用浏览器网格作判据。距离/体积数值容差为 1e−6；连接的最小重叠体积默认 0.1 mm³。正常入口面和声明的合法连通区域不作为剩余壁厚检查面。STEP 每次导出后重新导入，检查单一有效实体与体积差小于 0.01 mm³。

## 文件结构与输出

| 路径 | 用途 |
|---|---|
| `projects/saved/<id>.json` | 命名项目状态、工程主库 ID 及独立构建指针 |
| `projects/saved/history/<id>/` | 项目修订历史 |
| `projects/demo.json` | 旧开发/证明夹具，不用于正常启动 |
| `manifold/schema.py` | 版本化设计数据模型 |
| `manifold/geometry.py` | BRep 切削与审查几何 |
| `manifold/validation.py` | 确定性工程规则 |
| `manifold/store.py` | 原子持久化、版本与构建产物 |
| `manifold/server.py` | 本地 API 和静态界面 |
| `web/` | Three.js 查看器与编辑控制台 |
| `output/current.json` | 旧开发 CLI 的构建指针；用户项目使用各自记录中的指针 |
| `output/builds/<build_id>/` | 每次构建的不可覆盖快照 |
| `output/proof/` | 故意错误与修正后的示例及报告 |

每次构建输出 `production.step`、`review.json`（含真实实体离散网格、油路 ID 和位置）、`design.json`、`validation.json` 和 `validation.md`。所有输出共享设计 SHA-256；审查模型可由本控制台显示。未部署任何服务到云端。钻孔表、堵头清单、制造图以及原理图驱动的布局/路由可以在现有数据结构上后续扩展。

本地 API 仅允许固定文件与构建目录，不接受路径或可执行 CAD 代码；拒绝外部 Host/Origin、缺失本地请求标头、超过 8 MB 的 JSON 输入（图纸上传为 20 MB）。没有跨域开放。CSP 脚本仅限本源，样式内联仅用于 Three.js DOM 标注的位置和数据颜色。

技术参考：[CadQuery 安装](https://cadquery.readthedocs.io/en/stable/installation.html)、[CAD API](https://cadquery.readthedocs.io/en/stable/classreference.html)。


## SQLite 工程主库与引导工作流

- SQLite 是唯一运行时工程主库。项目只保存 cavity、可选 Cartridge、external-port 等稳定 ID 及项目状态；完整定义不会写入项目 JSON。
- cavity 放置、Cartridge assignment 和 schematic intent 是三个独立概念。放置 cavity 不会创建 Cartridge 或 schematic component；空 assignment 不触发对应验证。
- Cartridge compatibility 只来自 SQLite 的显式多对多关系，不通过自由文本或型号相似度推断。
- 运行时所需的主孔、全部 active footprint 子孔、液压窗口、offset、边界和加工数据在一次性导入时组合进可执行定义。没有 footprint 的 cavity 依据自身工程数据判断是否可用。
- Smart Align、即时预览、精确 OCCT/BRep、路由冻结/细化、STEP 往返、制造输出和 Drawing Workspace 继续从后端按 ID 解析本次所需定义。
- Validate 只为路由可修复的失败生成自动路线候选；显式 Optimize 仍可按用户操作比较自动网络的成本。

初始化、项目转换和启动失败语义见 [SQLite engineering library](docs/SQLITE_ENGINEERING_LIBRARY.md)。

V1 hydraulic sizing and displayed-route refinement: [behavior and regression evidence](docs/HYDRAULIC_SIZING_REFINE.md).

V2.3 CAD execution reliability: [process isolation, deadlines, diagnostics and measured evidence](docs/CAD_EXECUTION_RELIABILITY.md).
