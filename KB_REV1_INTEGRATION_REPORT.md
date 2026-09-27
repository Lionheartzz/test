# KB REV1 整合验收报告

## 范围与输入

代码基线为 `codex/sqlite-domain-reset` 的 `1fc4e4a97a1a77c94840b7c770353d3eae6d7f8b`。本次从 `PMC_MDTools_Library/PMC_MDTools_Master_Library_2026R2_Merged` 重建工程库，显式读取桌面上的 `KB_REV1_2026-09-26.zip`，并以现用 `data/pmc_engineering.db` 为只读 v2 自定义定义来源。交付库为 `data/pmc_engineering.rev1.db`（schema v3）；**未替换现用库，也未修改 MDTools Master**。现用 v2 库在切换前不能满足新运行时的 v3 校验；验收服务器均通过进程级 `PMC_ENGINEERING_DB` 指向 staging 库或它的隔离副本。

重建命令：

```powershell
.venv\Scripts\python.exe -m manifold.import_mdtools `
  --source PMC_MDTools_Library\PMC_MDTools_Master_Library_2026R2_Merged `
  --knowledge-package "$env:USERPROFILE\Desktop\KB_REV1_2026-09-26.zip" `
  --output data\pmc_engineering.rev1.db `
  --preserve-custom-from data\pmc_engineering.db
```

批次记录中的 ZIP SHA-256 为 `bd02e61ea7b92c747ec6e5f7942e4c4618a27a236d49d083a3c0a48cd9df3a16`，包版本为 `KB_REV1`，输入关系数为 15,272。MDTools `cavities_master.jsonl` 的 SHA-256 为 `7de42bc653b1e28c830739afbc7dbc2c8d384bd8f15e0554fba62ee2d7159b77`，导入器对 ZIP 内副本作逐字节哈希核对。现用 v2 数据库前后 SHA-256 均为 `98b1da75d3739da2c49729ff315bf2a59cab17f5d73d5b8b74fff8f4db43f831`。

## Staging SQLite 实测结果

以下数量从 `data/pmc_engineering.rev1.db` 的表和 `kb_import_batches.report_json` 读取，而非照抄 ZIP 预检数字。

| 指标 | 数量 |
|---|---:|
| 输入关系 / 保存的 evidence | 15,272 / 15,272 |
| Cartridge 身份 | 15,005 |
| 物理 cavity（含 3 个保留的 legacy 定义）/ 外部油口 | 6,429 / 446 |
| RESOLVED / REFERENCE_ONLY_SUPPLEMENT / TYPE_MISMATCH | 15,266 / 5 / 1 |
| CONFIRMED / PROBABLE | 12,508 / 2,764 |
| 执行准入关系 / 已解析但被 policy hold | 12,498 / 2,768 |
| Evidence→physical links / 执行兼容物理对 | 30,484 / 24,948 |
| 重复 relation ID / master ID 不匹配 / 缺失 runtime canonical ID / 拒绝导入 | 0 / 0 / 0 / 0 |
| 有多个不同 logical cavity 的 Cartridge / 有多个 physical ID 的 Cartridge | 106 / 12,321 |

10 条 CONFIRMED 未获执行准入：4 条低于 0.85、5 条仅有 supplement 身份、1 条类型不匹配。低置信度 relation ID 为 `REL:5f6505db6c925ddf`、`REL:9a889336111ea9ab`、`REL:a39b958ee50624f9`、`REL:c4965ee54b6f26c1`，置信度均为 0.50。类型不匹配 `REL:cc2c63b08c5f261c` 的两个候选 physical ID 在运行时均为 `external_port`，而 expected type 为 `cavity`；完整候选 ID、单位和失败原因保存在 `resolution_detail_json`。

兼容事实与几何可用性分别保存：24,948 个兼容物理对中 4,112 个对应不可用几何；2,003 个 Cartridge 的所有兼容 physical cavity 均不可用。执行前仍由现有定义可用性及设计验证约束。三条旧 `legacy_*` cavity 的全部字段和 6 条 interfaces 与 v2 源逐项相等。`PRAGMA integrity_check` 为 `ok`，`foreign_key_check` 为 0 条。

## 可重复重建与行为

同一 MDTools 源、同一 ZIP、同一 v2 保留源分别生成 `data/pmc_engineering.rev1.db` 和全新的 `output/kb-rev1-repeat.db`。比较排序后的主键集合和计数，四类完全相同：Cartridge 15,005、evidence 15,272、links 30,484、兼容物理对 24,948。批次导入时间不参与比较。导入器继续拒绝覆盖已存在的目标文件；重复 relation ID 内容冲突时失败。

AI 自动选择先按 evidence 的 `master_record_id` 形成 logical cavity 组。仅一个组时，只有恰好一个**可用且与 project context 单位匹配**的 physical definition 才能自动选择；不同 logical 组不自动择优。没有 evidence 来源的手工兼容按各 physical ID 独立成组。PROBABLE、低置信度 CONFIRMED、supplement 和解析失败记录只可查询证据，不能进入自动兼容候选。

## 验证

Synthetic ZIP 测试覆盖 25 字段保真、稳定 Cartridge ID、logical SHA-1 重算、双单位 crosswalk、冲突重复 ID、结构化解析诊断、准入边界、只读 v2 保留源、旧 definitions/interfaces、双库键集合一致性及三个 evidence API。AI 测试覆盖同 logical 双物理 ID 的单位选择、不同 logical 歧义、无匹配单位阻断、evidence-only 阻断，以及设计引用校验不会因 evidence 放行。UUID 测试覆盖原生 `randomUUID()`、LAN `getRandomValues()` 回退、缺少安全随机源时报错、各 ID 与 owner 格式。

前端 `node --test --test-isolation=none tests/*.test.mjs`：35 通过；Vite build 通过。`python -m manifold prove` 通过（corrected：268 PASS、1 WARNING、0 FAIL；invalid：295 PASS、2 WARNING、6 预期 FAIL）。冻结工程源后的完整 Python 回归为 **299 passed**；随后增加的旧版自定义油口/thread 依赖与错误 logical ID 诊断测试，所在 KB 测试文件再跑为 **3 passed**。当前测试集合为 300 项。

真实浏览器使用隔离项目和 staging 库副本，未操作普通用户项目。LAN 地址 `http://192.168.1.6:8765` 上实测 `isSecureContext === false`、`crypto.randomUUID` 不存在、`crypto.getRandomValues` 可用。Guided 新建并保存草稿，4 个 PORT ID 符合 `PORT_[0-9a-f]{32}`；预览请求返回 200，`X-PMC-Preview-Owner` 为完整 UUID v4；AI 上传测试 PNG 并保存，产生 `DOC_54fd0c13cc554621bdc0da6b805d8595`；从通过精确验证的隔离项目创建 Drawing、添加并保存 `sheet-40f88a6944f2`。Cartridge Lookup 逐项检查了 CONFIRMED 双单位 physical IDs、PROBABLE、低置信度 CONFIRMED、Sun supplement、类型不匹配和 Cavity 反查，截图做过视觉检查。

`127.0.0.1:8765` 与 `127.0.0.1:8766` 已被其他进程占用，故 staging 的 localhost 浏览器验收改在独立 `http://127.0.0.1:8767` 进行；该 origin 的 `isSecureContext === true`、`crypto.randomUUID` 可用。实测 Cartridge Lookup 返回真实 5 条 SC1F 搜索结果，并展示 4 个 logical cavity 组各自的 inch/metric physical ID；更新后的 Cavity 反查显示 28 条完整来源证据和分页计数。视觉检查通过。未停止或覆盖占用端口的其他服务。

视觉验收截图保存在 `.playwright-cli/page-2026-09-27T02-10-07-052Z.png`（LAN）和 `.playwright-cli/page-2026-09-27T02-29-19-512Z.png`（localhost）。
