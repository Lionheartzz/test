# PMC Manifold Studio

本地优先的参数化液压阀块工程 MVP。Python / CadQuery / OCCT 生成真实 BRep 实体与 STEP；Three.js 只负责显示由同一实体离散化的审查模型。无需登录、数据库、云服务或 AI API。

## Windows 启动

本机依赖已安装。双击 `Start-Manifold.cmd`，或在项目目录运行：

```powershell
.\Start-Manifold.ps1
```

打开 <http://127.0.0.1:8765>。服务只监听回环地址。关闭运行服务的终端或按 Ctrl+C 停止。再次启动不会覆盖已有项目。

另一台 Windows 电脑：安装 **Python 3.11 x64、Node.js 22.12+ 或 24 LTS**，然后运行：

```powershell
.\Start-Manifold.ps1 -Setup
```

首次安装需要网络；安装完成后的建模、校验、网页和导出都在本地运行。脚本使用 `requirements-lock.txt` 和 `package-lock.json` 固定已验证依赖，不修改系统 Python。若 PowerShell 执行策略阻止脚本，使用同目录的 `.cmd` 入口。

本机实际运行结果、最终构建标识和截图见 [VERIFICATION.md](VERIFICATION.md)。

Windows CAD 依赖已固定版本；`manifold/cad.py` 会先加载 CasADi 再加载 CadQuery，规避本机已复现的 NLopt/CasADi DLL 加载顺序导致的退出堆错误。新增 CAD 代码也应从这个模块导入 `cq`，不要绕过它。自动化测试包含真实子进程的正常退出检查。

## 日常设计

1. 在结构树或 3D 中选择阀块、孔腔、油口或钻孔。
2. 右侧编辑尺寸、安装面、坐标、油路、堵头及预期连接。
3. 点击“保存 · 重建与校验”。草稿不会立即影响已构建模型，未重建时标为 DRAFT。
4. 查看 PASS / WARNING / FAIL；报告中的每一条都有相关项、实际值、要求值和单位。点击问题定位相关特征。
5. 在当前构建为 PASS 时下载生产 STEP。失败构建也保留诊断 STEP，但网页禁止下载为生产输出。

拖动旋转、右键拖动平移、滚轮缩放；支持适配、俯视、等轴测、实体/内部审查模式、阀块透明度、各油路/孔腔/钻孔/标注显隐。

“编辑项目 JSON / 孔腔库”支持增删特征、修改规则和添加定义。后端严格校验完整数据，未知字段和无效引用会被拒绝。编辑时未保存的网页草稿会受到离开页面提醒；“重新读取”会明确提示丢弃草稿。

## 和 Codex 协作

权威文件是 **`projects/demo.json`**。孔腔库直接内嵌在项目中，构建无需隐藏 CAD 脚本状态。可以直接告诉 Codex：

- “把 CV2 沿 X 移动 15 mm，重建并检查连接。”
- “把 RV1 改到前面，并调整相关钻孔，保留 7 mm 最小壁厚。”
- “减少 P 油路的堵头，给出通过检查的方案。”

Codex 修改结构化项目数据后运行：

```powershell
.\.venv\Scripts\python.exe -m manifold build
```

网页每 5 秒检查磁盘设计和构建版本；无草稿时自动更新，有草稿时保留它并提示冲突。保存请求必须携带读取时的 SHA-256，磁盘已变化则返回 409。所有 CLI/API 构建使用同一文件锁；构建期间检测到直接文件修改时放弃提交。API 保存旧项目到 `projects/.history/`，输出先写入独立目录，成功后原子切换指针。直接编辑 JSON 时建议一次性原子替换文件；CLI 不会为手工编辑之前的内容自动建备份。

## 坐标与连接

单位统一 **mm**；原点在阀块左前底角，X=长度，Y=宽度，Z=高度。

| 面 | U | V | 进刀方向 |
|---|---|---|---|
| left / right | Y | Z | +X / −X |
| front / back | X | Z | +Y / −Y |
| bottom / top | X | Y | +Z / −Z |

`depth` 是圆柱部分深度；118° 钻尖的额外深度由几何引擎计算并参与壁厚检查。180° 表示平底加工。首版只支持从六个外表面垂直进刀的直线钻孔，不支持任意斜孔或曲线通道。

- `cavity`：使用 `definition` 引用库定义，各轴向液压窗口分别通过 `circuits` 指定油路，例如 `CV1:upper` 和 `CV1:lower`。
- `port` / `drilling`：使用独立 `circuit` 字段。颜色由工程 ID 决定，永不通过颜色推断油路。
- `connects_to`：声明**直接几何连接**，如 `G-P` 的 `P, CV1:upper, RV1:upper`。传递连通性由测得的连接图计算。
- 所有实际接触都必须声明；漏声明的同油路接触也报错。零体积相切不视为通油。
- 堵头占据从入口开始的 `plug_length`，该体积从流体节点中移除；其他切削不得进入堵头啮合区。
- 每个无堵头钻孔必须有同面、同轴、同油路且尺寸足够的外部油口封闭入口。

## 插装孔库与工程边界

当前提供三个明确标记 **demo_only** 的示例：双区阶梯孔、紧凑双区孔、单区服务孔。它们由真实圆柱切削体构成，但**不是 SUN / HydraForce 的厂家孔腔**。

库定义包含来源、阶梯切削尺寸、液压窗口、安装工具空间和螺纹注记。添加真实库时必须按厂家图纸核对来源与版本、全部尺寸、公差、表面、密封分区及工具空间。当前内核支持连续且直径不递增的圆柱阶梯；需要锥面、退刀槽或完整螺纹的厂家孔腔须扩展切削模型后才能声称精确实现，不能仅改 `demo_only`。

**加工空腔与装阀后的油路不同**：真实未装阀孔腔是连续切削体，液压校验则按已安装密封阀芯的接口窗口建图。同一孔腔的不同窗口不会自动串联；窗口外的孔壁/密封/螺纹区域禁止其他钻孔侵入。首版不模拟阀位及阀内流动。

PASS 仅代表当前规则范围通过，**不是制造放行或承压认证**。材料为工程元数据；压力、疲劳、流量、压损、热、污染、完整刀具/夹具干涉、螺纹强度及密封性能尚未计算。油口目前为尺寸可配置的直孔，类型和规格为注记，尚未实现 SAE / BSP 等标准完整接口。外部工具干涉使用声明的圆柱包络。

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
| `projects/demo.json` | 当前权威项目及孔腔库 |
| `manifold/schema.py` | 版本化设计数据模型 |
| `manifold/geometry.py` | BRep 切削与审查几何 |
| `manifold/validation.py` | 确定性工程规则 |
| `manifold/store.py` | 原子持久化、版本与构建产物 |
| `manifold/server.py` | 本地 API 和静态界面 |
| `web/` | Three.js 查看器与编辑控制台 |
| `output/current.json` | 当前构建指针及设计 SHA-256 |
| `output/builds/<build_id>/` | 每次构建的不可覆盖快照 |
| `output/proof/` | 故意错误与修正后的示例及报告 |

每次构建输出 `production.step`、`review.json`（含真实实体离散网格、油路 ID 和位置）、`design.json`、`validation.json` 和 `validation.md`。所有输出共享设计 SHA-256；审查模型可由本控制台显示。未部署任何服务到云端。钻孔表、堵头清单、制造图以及原理图驱动的布局/路由可以在现有数据结构上后续扩展。

本地 API 仅允许固定文件与构建目录，不接受路径或可执行 CAD 代码；拒绝外部 Host/Origin、缺失本地请求标头、超过 1 MB 的输入。没有跨域开放。CSP 脚本仅限本源，样式内联仅用于 Three.js DOM 标注的位置和数据颜色。

技术参考：[CadQuery 安装](https://cadquery.readthedocs.io/en/stable/installation.html)、[CAD API](https://cadquery.readthedocs.io/en/stable/classreference.html)。
