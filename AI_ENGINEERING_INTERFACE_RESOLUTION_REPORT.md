# AI 元件到工程接口解析修复

起始 HEAD：`fc8e8053315fc981304fecb4bba3a18cf7c3905f`。分支：`codex/sqlite-domain-reset`。

## 通用根因

1. AI 契约只有 `cavity`，缺少独立的安装接口观察字段。产品型号、驱动方式和安装接口没有得到完整区分。
2. 生成预检对全部组件先调用 cartridge 身份解析；没有 cartridge 匹配就不提供自动工程接口候选。已知安装接口无法独立于产品 SKU 使用。
3. 工程库的同一个 `CavityDefinition` 容器已经承载 cartridge 腔型和板式安装面的源几何。界面却统一称其为 cartridge/cavity，造成错误引导。
4. 搜索直接对原始文字作 SQL 子串匹配，没有通用的标准名称/格式处理；结果只显示源标准代码。Enter 未绑定搜索，同一面板的旧请求还可能覆盖新请求。
5. 导入的关联 footprint 窗口有应用前缀，例如 `a_A`。原映射把整个 ID 当作液压标签，无法匹配实际端口 `A`。

这些问题与某一个阀的 SKU 无关，没有为 AH4D 添加特殊规则。

## 修改

- 分析契约 v8 增加可选 `mounting_interface` Observation。保留 `cavity` 和既有字段；新字段采用相同的来源、certainty、页码、原文及身份准入规则。旧分析可继续读取。
- 产品身份、腔型声明及安装接口声明分别解析。明确、已确认的工程接口可以绑定现有物理定义，不以 cartridge SKU 为必需条件。
- 若产品已经解析为 cartridge，自动候选继续使用执行兼容白名单，并与显式接口声明核对。冲突不会通过猜测或替换消失。
- 标准族名称可能对应多个物理变体。只在项目单位下恰有一个可用定义、且源端口标签可一一对应时自动选择；其他情况保留人工决策。
- 搜索继续读取现有 SQLite 定义，增加按 DB 路径/mtime 缓存的小型身份索引。支持名称、源 family、标准及大小写/标点/空格变体，不在运行时读取 MDTools 源包或构建 BRep。
- ISO 4401 标准别名覆盖 CETOP 3/5/7/8/10 和 NG6/10/16/25/32 的已核对常用族。其他已有工程族仍通过其源名称/family 搜索。别名仅作查询和显示，不合并镜像、先导端口或其他物理变体。
- 新 API role 为 `component-interface`，原 `cartridge-cavity` role 保留兼容。
- Enter 和按钮调用同一个搜索操作，保留请求代次及页面存活检查。不可用定义可以查看，选择按钮禁用。
- 源应用前缀仅在显示及标签匹配时还原；canonical ID、几何和偏移不变。TA/TB 不合并为 T，P/A/B/T 不推断成 cartridge 的 1/2/3/4。

标准命名核对来源：[Parker 工业阀目录](https://www.parker.com/content/dam/parker/msg/hydraulic-valve-systems-division/PDF-files/catalogs/legacy/legacy-industrial/Cat-HY14-2533-Industrial_03-08.pdf)、[Parker 电液阀目录](https://www.parker.com/content/dam/Parker-com/Literature/Hydraulic-Valve-Division/Catalogs/Catalog-PDFs/Cat-MSG14-2550-Electrohydraulics.pdf)。这些文献没有用于添加或修改任何加工尺寸。

## 实际检查

- Vite build 完成；保留既有运行时字体 URL 和 bundle-size 提示。
- LAN 服务重载前确认无正在运行的 AI 作业。localhost / LAN 服务均可访问。
- 在 LAN 浏览器打开用户已完成的真实分析，未点击 Start analysis。
- 用 Enter 搜索 `CETOP-5`、`NG6`、`ISO 6264` 和 `CETOP 5`；确认不同接口族、源 family、单位及端口列表可见。
- 确认镜像和 TA/TB/X/Y 变体没有折叠成同一物理定义，不可用定义的选择按钮禁用。
- 在独立浏览器标签的临时预检中选择现有 metric 四端口安装面 `4401-05-04-0-94`，P/A/B/T 按源标签对应。AH4D 的接口阻塞消失，未要求 cartridge SKU。
- 预检仍保留 DSCS/LRHC 两项端口映射决策。没有按相同端口数量补造映射。未生成/保存项目或 CAD。
- 交互截图：`output/ai-interface-search-acceptance.png`。
- `git diff --check` 通过。未运行 Python/JS 测试套件、prove 或 CAD 回归，未调用付费 AI。

新 `mounting_interface` 字段的真实 AI 输出遵循情况未通过新 provider 请求验证。旧保存分析不会自动改写；新提示契约用于下一次操作员主动分析。本报告不宣称整个原理图已完成 CAD 或制造验证。

## 保护的数据和范围

以下 SHA-256 与本任务前相同：

- `data/pmc_engineering.db`：`1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`。
- `.pmc-local/ai-provider.json`：`2585ed2e0e32ff5677cf0d3136fdd948f7a9c9cf951eb6683df969cf742e190a`。

未修改 SQLite schema/data、cartridge 兼容事实、MDTools Master、CAD 几何、Routing、Drawing、STEP 或 provider 配置。构建与浏览器交互用于这次前端修复生效，未启动广泛审计。

## 修改文件

- `manifold/ai_design/interface_catalog.py`：共用现有定义的身份/查询适配器。
- `library_resolution.py`、`generation.py`、`api.py`：通用工程接口预检、声明核对、兼容 API role。
- `semantic.py`、`service.py`、`identity_admission.py`、`diagnostics.py`：新可选观察字段及其安全准入/诊断版本。
- `web/ai-generation.js`、`web/ai-diagnostics.js`：Enter、通用接口显示、源端口标签及友好诊断。
- `docs/PROVIDER_DIAGNOSTICS.md` 和本报告。

提交及已核实的远端 SHA 见完成回复。
