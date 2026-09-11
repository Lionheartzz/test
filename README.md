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

1. **New Manifold** 五步完成阀块、Metric/Inch 上下文、网络与油口、元件选择、放置与接口分配、复核。每个网络独立配置 0–8 个外部油口，每个油口可选择面、规格及已有 PMC/MDTools 加工定义，也可保留 Custom straight bore；名称使用 P/T/A/B 或 P1/P2。支持 Cartridge first 查询明确记录的兼容关系，也支持 Cavity first 后查看已知型号或保留未知兼容状态。可以暂不选孔型；新项目只包含本次选择的定义。工程坐标始终为 mm，界面保留完整编辑入口。**Import Project / Export Project** 是 AI 和人工设计的共同入口。导入 `.pmc.json` 后查看摘要并创建独立项目草稿；导出保留完整孔型版本、连接意图和复核决定，即使草稿还没有 PASS。项目 JSON 上限 8 MB，图纸二进制仍单独存放在本地 assets。
2. **Schematic** 上传 PDF、PNG 或 JPEG。AI 提供者与模型信息属于可携带的项目来源字段；AI Design 可调用用户配置的服务生成草稿。可选 Codex handoff 收在展开项中，通用 AI 交付格式见 [AI_PROJECT_CONTRACT.md](docs/AI_PROJECT_CONTRACT.md)。
3. **Engineering Review** 管理假设、尺寸、选型和连接疑问。接受或解决事项必须填写决定；元件确认检查实际孔腔接口网络。对当前项目使用的孔型，可点 **Edit pinned definition** 修改并重新映射接口。
4. **Cavity Library** 按单位、制造商、类型、螺纹和关键词分页查询完整 MDTools 转换库。原生记录和独立 footprint 关系保持结构化；可插入、编辑、复制、删除及恢复目录项。PMC 修订保存在 `projects/library/`，项目内固定定义不随目录更新。材料、加工规则及其他工程资源可查看并固定到项目。
5. 元件支持 Duplicate、Replace、Suppress、Delete、换面、位置与网络编辑。六面孔口中心及附近均可开始拖动，悬停高亮、grab / grabbing 光标显示状态；完整安装包络限制边界，默认 1 mm 吸附、Alt 暂停。Undo / Redo 可撤销草稿操作。
6. 三维中直接点击生成的钻孔可检查其网络、尺寸和位置；**Refine in 3D** 固定该回路当前分段，可从可见钻孔整段悬停、选中和拖动，中点环仅为辅助。拖动结束后尽可能延长相连正交支路以保留交点，并运行精确草稿检查。端口位置不会被擅自移动；破坏入口封闭、壁厚、连接或通油开口的调整仍报 FAIL。**Hydraulic Nets** 区分连接意图和派生钻孔；优化比较正交轴顺序、入口和偏移路径，最多六个精确候选。默认未指定方案的自动路由也进行最多六个候选的精确比较，以实际 FAIL、WARNING 和综合加工代价选择不退步方案；代理风险仅用于安排候选，不能优先于已验证方案的加工成本。参数拖动预览仍明确标为未验证；默认偏好最小壁厚之外额外 4 mm 的余量，以软惩罚与钻深、钻孔数和堵头数权衡，可在 Block & Constraints 修改。最小壁厚硬规则不变。失败候选也保存到 `output/optimizations/`。优化期间草稿变化会阻止覆盖。该有限搜索不保证任意布局都找到可行路线。
7. **Save & Validate** 保存并生成精确 OCCT 实体、校验和不可变构建。**Solid** 显示实际加工孔口，Drillings 可独立叠加钻孔。精确结果未就绪或生成失败时保留当前预览并显示状态；未保存草稿会按需生成精确切削预览，明确标记未校验且不写入项目或构建。**Internal Review** 显示孔腔阶梯/锥面，**Hydraulic zones** 可独立关闭。普通拖动预览仍是参数预览。当前 PASS 才开放 STEP；加工清单保留原生配方与未解析表达式，`manufacturing_ready` 独立于几何结果。

运行时仅读取 `PMC_MDTools_Library/PMC_Library_Converted_v05` 的转换工程目录；不读取 MDB、raw 归档或 QC 报告。Metric / Inch 原始值与单位身份保留，精确 CAD 使用 mm。库含 2477 / 841 个公制 / 英制孔腔及 3915 / 1649 个独立 footprint。全量载入审计：3318 个孔腔无损，3077 个尺寸映射、241 个待几何映射复核。尺寸映射不等于厂家批准。

241 条待复核记录仍可查看、插入及派生 PMC 解释。原始 MDTools 记录、关联记录和来源 SHA 保持只读；编辑作用于独立的 PMC interpretation，不覆盖导入文件或把原始记录改成修订值。待复核状态不会因数据保留完整而自动解除。逐条来源及文件哈希审计见 `output/library-preservation-v5.json`。

原生切削支持圆柱、锥面、显式环槽及旋转后的 footprint 偏移。Sun locating-shoulder 基准和不能自动应用的特殊槽等保留待复核状态；线程、容差、刀具和 `$STEP*` 配方保留完整数据，不伪装成已执行加工。演示孔腔仍是演示尺寸。多选、完整刀具执行和尺寸工程图边界见 [DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## AI Design · 原理图生成可编辑三维草稿

从 **AI Design → Provider settings** 自行填写 API 地址、多模态模型名和密钥，没有预设厂商或模型。上传 PDF / PNG / JPEG，输入工程要求，选择配置的模型并点击 **Analyze & create manifold draft**。确认未解决的孔腔选择和液压窗口映射后，系统使用已有库几何、自动布置/布线和精确校验生成草稿；通过 **Open draft in Manifold Studio** 进入普通项目编辑、保存和校验。

当前支持 Chat Completions 图像输入接口。所选图纸和要求会发送给你配置的服务；凭据仅存服务器本机忽略目录，不随项目导出。无需凭据也能使用明确标识的本地 mock 演示流程，但 mock 不代表真实识图效果。第一版最多 4 个插装阀，采用有限候选搜索；未知接口、兼容性和无法执行的要求保留人工审核。已测试本地模拟服务传输及实际孔腔 CAD 流程，未验证付费远端模型识别准确率。

配置步骤、工程边界与失败恢复见 [AI Design 使用说明](docs/AI_DESIGN_LAYER.md)，验证证据见 [VERIFICATION](VERIFICATION.md)。

## 和 Codex 协作

当前打开项目的权威记录为 **`projects/saved/<id>.json`**，包含独立 design、更新时间、归档标记与构建指针。**Save Project** 保存未通过校验的工作进度；**Save & Validate** 保存并构建。Projects 可搜索、重命名、复制、归档和恢复项目。Delete permanently 要求输入完整项目名，删除该项目记录及修订历史；共享库、源记录、assets 与不可变构建证据保留。每次启动先展示项目库，不自动打开 demo。`projects/demo.json` 与 `manifold.demo` 只用于开发、旧 CLI 与工程证明，不自动进入用户项目库。孔腔库的固定版本内嵌在项目中，命名 nets 表达液压意图，自动钻孔保存在构建的 resolved_design.json；构建无需隐藏 CAD 脚本状态。可以直接告诉 Codex：

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

库定义包含来源、阶梯切削尺寸、液压窗口、安装工具空间和螺纹注记。添加真实库时必须按厂家图纸核对来源与版本、全部尺寸、公差、表面、密封分区及工具空间。当前内核支持显式圆柱阶梯、锥面/锥底、环状切削体，以及带局部偏移和旋转的 footprint 切削。完整螺纹牙型和尚未映射的特殊退刀槽不自动生成；仅保留原始配方并不代表已执行该加工，也不能仅改 `demo_only` 就宣称厂家精确实现。

**加工空腔与装阀后的油路不同**：真实未装阀孔腔是连续切削体，液压校验则按已安装密封阀芯的接口窗口建图。同一孔腔的不同窗口不会自动串联；窗口外的孔壁/密封/螺纹区域禁止其他钻孔侵入。首版不模拟阀位及阀内流动。定义的 `usage_role` 明确区分 cartridge-cavity 与 external-port；跨角色复用必须记录 `usage_decision`，单个居中窗口本身不构成油口资格。

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
| `projects/saved/<id>.json` | 命名项目、固定定义及独立构建指针 |
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


## 2026-09-09 引导工程工作流

- 工具按真实 `tool` + `family` 查询：drill 305、flat_bottom_drill 43、spot_face 64；材料按 `material_stock` 查询，共 268。完整记录优先于索引摘要。
- 库新增显式 lineage（导入、PMC 派生、PMC 自建、演示/暂定）、来源 SHA、派生关系和修订历史，兼容旧版本 1 项目与旧库存储哈希。兼容型号需记录来源和复核状态，不从孔型名称推断。
- 放置支持数量、初始面与接口网络；Smart align 可选吸附已生成自动路线、手动路线、外部油口中心线、旋转后的液压窗口、原点及阀块中心，黄色线显示候选，Alt 暂停。XYZ 原点与选中对象的全局/面 UV 坐标可见。
- 二维剖面/顶视图可选择切削步骤、液压接口和边界，显示直径、深度基准、锥角、环槽内外径及偏移，并随数值输入实时更新；螺纹/密封数据没有已映射轴向范围时以来源文本保留。完整原生记录继续保留。明确闭合的源 `L` 线段轮廓作为独立安装边界；无高度时只代表平面安装区，不能当作完整阀体或服务空间。
- 自动候选可复用偏置相交的单个油口钻孔，也可在允许时提出两终端斜孔方案。有限搜索仍由精确验证裁决；不保证任意布置可路由。冻结后可逐段手工修改，Reroute 删除该网冻结的派生段并重新生成。
- 通油面积筛查取重叠体质心处沿两个流向的精确 BRep 公共截面面积之小值，输出等效直径。给定网络流量/流速时，小于要求的连接报 FAIL 并不计入有效连通图。这是可复现的**特征开口筛查**，不保证全路径最小喉口，不是压损、CFD、制造或承压认证。
- `output/library-mapping-v4.json` 保留全部 241 条暂定映射及原因；界面 Provisional mapping report 可重新查看。几何映射和加工配方复核独立。

## 原始数据库与边界语义核查

源数据核查范围与结论见 [MDTools source audit](docs/MDTOOLS_SOURCE_AUDIT.md)。运行应用只读取转换工程库；原始 MDB 审计是单独的只读开发工具，不是应用运行依赖。原始库文件不被改写。

Footprint envelope 保留来源角色、源形状类型、原始语法和 SHA。独立 AssemblyEnvelope 记录不按名称匹配孔腔或阀型号。Library 中可由工程师显式选择目标孔型、mounting/body/service/tool 角色与高度，再将原始记录固定到项目；该选择单独标为 engineer-selected，并保留复核项。高度 0 仅为平面区域。明确闭合直线轮廓与显式 Circle 的完整四圆弧记录可生成精确边界；未支持的一般曲线语法保留原文并要求独立映射。
