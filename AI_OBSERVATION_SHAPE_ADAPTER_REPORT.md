# AI Observation 简写适配修复

起始 HEAD：`28d6d315905e3e31464b71e71f8cfc0a7e3275e5`。
分支：`codex/sqlite-domain-reset`。

## 已确认的真实失败

- 保存的 run：`5a47d56c0d4c41469e700e4e19810c95`，2026-10-09 09:56:45 +08:00。
- `agnes-3.0-flash`，1 次请求、0 重试，耗时 122.37516 秒。
- HTTP 200、`finish_reason=stop`、stream 完整结束。
- 失败阶段：`structured_output_validation`，prompt v8。
- 43 个错误全部为 `model_type`：8 个 manufacturer、8 个 model、27 个 net。
- 原记录没有保存输入类型或原始响应；不能断言当时每个值具体是 string/null，也不能从诊断恢复原分析。

## 根因与实现

原 provider 适配层直接要求每个观察字段都是完整 Observation 对象，且安全恢复只针对已包装的可选身份语义错误。整个液压分析因此会因紧缩的 scalar/null 写法被拒绝，即使这些写法可以保守地表示为未确认观察。

新增 `observation_adapter.py`，仅在 provider 边界处理已知 Observation 位置：

- `null` → 默认 unknown/null，没有值或来源声明。
- string/boolean/有限且可表示的 number → 原值、uncertain、ai_inference。
- 覆盖身份、功能、组件/外部端口 net、specification 和 parameter reading。
- 不插入缺失字段、不修改已包装对象、不解释数组、不借用组件来源、不补造原文或页码。
- 不改变实体列表、端口标签、disposition 或模型给出的 net 名称。网络分组仍由原有正常化逻辑处理。
- 转换后完整执行 `CircuitReading`、原有身份恢复及正常化/工程准入。重复标签、空/非字符串 net、blocked/terminated 与连接冲突、无效来源/页码/原文等仍拒绝。
- 所有其他 JSON/schema/canonical 合同保持严格；没有全局放宽类型或关闭校验。

转换并不等于确认：裸值只会成为未确认 AI 观察。compact intent 单独保留这些原值与单位供审阅；已确认 facts 和 identity_valid 判定不变。自动库身份、兼容关系、工程参数和 ratings 不使用这些未确认值。网络 status/kind 一并保留，界面明确展示推测连接的未确认状态。新分析含 uncertain 连接时，生成预检要求使用已有 topology decision 字段记录审阅决定；原始分析 claims 不会被改写为已确认。旧缺少该状态字段的分析保持兼容。

诊断增加固定 input_shape 类型元数据，仍不记录原值、raw response 或 credential。转换记录保留安全路径/action=normalized；后续真正错误保留 action=rejected。旧诊断的类型继续显示未知。

## 运行与范围

新契约版本为 v9；模型仍优先返回带独立来源的完整 Observation 对象。
不修改模型、token budget、reasoning、timeout、retry 或 JSON/streaming 设置，不发起任何新 provider 请求。

未修改 SQLite、MDTools Master、Routing、CAD、Drawing、STEP 或已保存项目。旧失败记录仍为失败，不回填成成功。

按此前要求，验证限于静态检查、保存诊断、前端构建/服务加载及 `git diff --check`；未添加或运行 Python/JS 测试套件、CAD suites 或 prove。没有原始响应，也未付费重跑，因此不宣称原 122 秒案例已通过真实复验。此修复覆盖可安全处理的 scalar/null 输入；数组和其他不合法输入继续拒绝。

## 保护文件 SHA-256

- 工程 DB：`1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`。
- provider 配置：`2585ed2e0e32ff5677cf0d3136fdd948f7a9c9cf951eb6683df969cf742e190a`。
- 原失败 current.json：`bffa7545bbe7a339fdc568421de5983b94fec22a8658b194c96cd615ad26432b`。

## 修改文件

`manifold/ai_design/observation_adapter.py`、`remote.py`、`diagnostics.py`、`validation_details.py`、`semantic.py`、`service.py`、`generation.py`；`web/ai-design.js`、`web/ai-diagnostics.js`、`web/ai-generation.js`；诊断文档和本报告。

最终构建、服务加载、提交和远端状态以完成回复为准。
