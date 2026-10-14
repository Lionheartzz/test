"""Read-only evidence summary. Does not run CAD, routing or Generate."""
import collections
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/runtime-checks/single-work-root-correction-20261014'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    snapshots={name:read(RUN/name/'result.json') for name in ('precheck','source','plug')}
    for saved in snapshots.values():
        assert saved['execution']['reason']=='COMPLETED'
        assert all(sha(ROOT/path)==value for path,value in saved['code_hashes'].items())
        assert saved['protected_before']==saved['protected_after']
    reference=read(ROOT/'output/runtime-checks/engineering-planner-20261014/protected-reference.json')
    assert len(reference)==13 and all(sha(Path(path))==value for path,value in reference.items())
    current=snapshots['precheck'];e=current['result']['evidence'];d=current['result']['design'];table=e['initial_calculation']
    assert e['source_layout_ready'] and e['process_gap'] is None and not e['catalog_searches'] and not e['deep_labels']
    labels={r['placement_id']:r['label'] for r in d['schematic_intent']['components']}
    for f in d['features']:
        if f['kind']=='port':labels[f['id']]=f['circuit']+' external port'
    checks=[]
    for p in sorted((RUN/'final-validation').rglob('acceptance.json')):
        r=read(p);assert r['status']=='EXACT_FEASIBLE' and r['topology']==dict(valid=True,solids=1) and r['step']['status']=='PASS'
        checks.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),status=r['status'],counts=r['validation']['counts'],
            topology=r['topology'],step=r['step']['status'],seconds=r['seconds']))
    assert len(checks)==4
    cycle_path=RUN/'final-validation/test_real_saved_positive_escap0/real-escape-cycle.json'
    cycle=read(cycle_path);assert cycle['after']['status']=='CONSTRAINT_DOMAIN_SOLVED_NOT_ADMITTED'
    tests=[]
    for name in ('final-validation.xml','manual-api.xml','repair-dependencies.xml'):
        tree=ET.parse(RUN/name);cases=tree.findall('.//testcase')
        assert not tree.findall('.//failure') and not tree.findall('.//error')
        tests.append(dict(path=str((RUN/name).relative_to(ROOT)),cases=[c.attrib for c in cases]))
    negatives={}
    for name in ('source','plug'):
        value=snapshots[name]['result']['evidence']
        measured=[m for step in value['decisions'] for m in step.get('measurements',[])]
        expected=524.2981254966872 if name=='source' else 66.39930264676538
        assert any(abs(m['value']-expected)<1e-8 for m in measured)
        negatives[name]=dict(volume_mm3=expected,failures=value['failures'],timing=value['timing'],
            execution=snapshots[name]['execution'],measurements=[next(m for m in measured if abs(m['value']-expected)<1e-8)],
            decisions=[{k:v for k,v in step.items() if k in ('kind','cause','committed','affected_nets','source_moved','unchanged_nets')}
                for step in value['decisions']])
    detail=table['coordinate_constraints'];values=detail['values']
    binding={a:[c for c in detail['constraints'] if c['high']==f'D{a}' and abs(values[c['high']]-values[c['low']]-c['distance'])<1e-6]
        for a in range(3)}
    decisions=[{k:({a:b for a,b in v.items() if a!='operations'} if k=='basis' else v) for k,v in row.items() if k not in ('after','constraints','actual')}
        for row in e['decisions'] if row['kind'] in ('HYPERGRAPH_SOURCE_ARRANGEMENT','CONTRADICTORY_PROCESS_REPLAN','INITIAL_SOURCE_CHECK')]
    data=dict(starting_head='d49815ac26ecda1decd136f0f77cd25a23fc1a20',scope='SINGLE_WORK_ROOT_CORRECTION',
        source=current['source'],code_hashes=current['code_hashes'],
        source_design={k:v for k,v in d.items() if k not in ('schematic_intent','origin','review_items')},labels=labels,
        source_layout_ready=True,process_gap=None,manufacturing_ready=False,complex_exact_executed=False,
        source_table=[{k:v for k,v in f.items() if k!='constraints'} for f in table['features']],
        spacing=table['spacing'],groups=table['groups'],associations=e['engineering_plan']['source_associations'],
        dimensions=table['dimensions'],binding_dimension_constraints=binding,selected_processes=e['selected_processes'],
        actual_drillings=e['actual_drillings'],failures=e['failures'],decisions=decisions,
        original_cycle=dict(path=str(cycle_path.relative_to(ROOT)),before=cycle['before'],after=cycle['after']['status'],
            first_decision=next(r for r in cycle['evidence']['decisions'] if r['kind']=='CONTRADICTORY_PROCESS_REPLAN')),
        negatives=negatives,exact_witnesses=checks,old_opening_operations=read(RUN/'opening/comparison.json')+read(RUN/'opening/native-options.json'),
        old_opening_pairs=read(RUN/'opening/pairs.json'),timing=e['timing'],execution=current['execution'],
        protected_files=reference,tests=tests,global_layout_queue=e['global_layout_queue'],catalog_searches=e['catalog_searches'],deep_labels=e['deep_labels'])
    path=ROOT/'docs/engineering/work-design-root-correction-evidence.json';path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    lines=['# 单工作设计工程布局根因整改', '',
        '基线 `d49815ac26ecda1decd136f0f77cd25a23fc1a20`，分支 `codex/sqlite-domain-reset`。', '',
        '**三个已确认的决策缺陷已整改；复杂工程仍未制造验收。** 本轮没有完整复杂 Generate、旧 Catalog、三维标签搜索、数据库修改或 CAD 规则放宽。', '',
        '## 根因与实现', '',
        '- 原 Top scaffold 被直接继承，`spacing()` 对同面所有元件施加单轴全排序，`groups()` 又把传递连通分量当成排列组。逐个最小化当前体积还会把前三个元件锁成条带。',
        '- `design_space.py:69` 将未锁定 AI Cavity 的默认域设为 Top/Front/Back/Left/Right；硬 Bottom 优先，Port 的独立六面域不变。`generation.py` 的 scaffold 同步排除默认 Bottom。固定 U/V 保留安装坐标系，固定 Rotation、未拥有/受保护元件保持原权限。',
        '- `engineering_plan.py:106` 从 Net 超图生成直接加权邻接：每个超边对源邻接贡献 `1/(源数量−1)`，多 Net 分别累加，窗口始终属于一个刚体。没有按名称或阀数量分支。',
        '- `source_arrangement.py:17` 在一个 WorkDesign 上按硬约束、耦合和实际包络定位；从五面、真实投影边界和窗口对齐事件选择坐标，非圆安装轮廓使用旋转后投影。直接关联元件的面积完成量估计避免贪心条带；不是硬行数、面配额或全局布局组合。',
        '- `single_design.py:133` 按实际分离投影保留二维关系；圆形使用 `Ri+Rj+Gij`，非圆形使用投影支持值与真实 wall/access gap。跨面种子约束只作用于本次构造的布局，不把原 Port scaffold 变成额外锁定。',
        '- `corridor_planner.py:110` 比较真实窗口对齐位移、三主轴、两入口、正/负逃逸、源支持、实际闭合占用、完整外钻深度及工具能力；`single_design.py:53` 不再直接取未评价的 `choices[0]`。这些是工艺调度估计，随后必须经过 materialize 和生产完整加工检查。',
        '- `single_design.py:290` 对真实最小正权环做条件约束传播并修改相关主轴/逃逸/轴向策略/平面等式。失败缓存包含整个 DecisionState；旧 Net 组合下的失败不能排除新组合下的同一工艺。仅选择的充分约束域被否定，不形成跨几何物理禁令。',
        '- `single_design.py:517` 优先真实入口，再比较局部工艺轴/逃逸，最后使用测量分离量移动源/加工坐标。全部保留孔参与生产筛查。失败事务依赖完整保留切削体，回滚恢复 operations；`affected():491` 包含真实安装轮廓、外向高度及第三方扫掠关系。`circular()`/`source_conflicts()` 均使用待查 Target 的 Block。', '',
        '## 新复杂源布局', '',
        '下表是生产约束求解和源安装检查后的实际坐标；显示值四舍五入，JSON 保留完整精度。所有调整仅属于这次新的 AI-owned 工作值，未写回原项目。', '',
        '| 元件 | Feature | 面 | U / mm | V / mm | Rotation |', '|---|---|---|---:|---:|---:|']
    for f in table['features']:lines.append(f"| {labels[f['feature']]} | `{f['feature']}` | {f['face']} | {f['u']:.6f} | {f['v']:.6f} | {f['rotation']:g} |")
    lines+=['', '选择原因逐项保存在 JSON 的 `decisions/HYPERGRAPH_SOURCE_ARRANGEMENT`：直接邻接权重、实际包络、允许面、投影面积和预计加工长度均可回查。侧面长 Cavity 的深度沿自身法向计算；Top 大安装轮廓与多窗口源按所有关联 Net 共同定位。Port 的 Bottom 属于其原有独立允许域，不代表 Cavity 默认开放 Bottom。', '',
        f"Block = **{table['dimensions'][0]:.6f} × {table['dimensions'][1]:.6f} × {table['dimensions'][2]:.6f} mm**。",
        '尺寸从源深度/安装投影、真实中心距、跨面分离、干线层、支路列、真实闭合占用和轴向安全停止区间联合传播，不是 Cavity 直径求和。实际紧约束：', '',
        '- X：MA/MB 走廊的外端 14 mm 余量；MB 的来源轴向窗口区间也绑定该上界。',
        '- Y：P 走廊外端 14 mm 余量。14 mm 来自已绑定闭合占用 10 mm + bore radius 4 mm；没有虚构压力 wall。',
        '- Z：Front RDDA 的实际安装投影上支持 15.875 mm。对面深度只在实际横向投影重叠时相加。', '',
        '这些空间仅证明当前工艺约束可表达，不证明其内的所有真实钻孔安全；压力、流量等 UNKNOWN 仍保留。', '',
        '## 八条 Net 的当前工艺', '',
        '| Net | 主轴 / 入口 | 逃逸 | 轴向来源窗口 | 真实孔数 | 前置结果 |', '|---|---|---|---|---:|---|']
    for n,p in e['selected_processes'].items():
        reasons=collections.Counter(f[0] for f in e['failures'].get(n,[]))
        lines.append(f"| {n} | {'XYZ'[p['spine_axis']]} / {p['entry']} | {'正' if p['side']>0 else '负'} | {', '.join(p['axial_members']) or '径向窗口'} | {len(e['actual_drillings'].get(n,[]))} | {dict(reasons) if reasons else '加工筛查清晰；连通性尚未 CAD 准入'} |")
    lines+=['', '所有表内路线均由生产 `propose/axial_route` 生成完整 Features，并绑定真实闭合定义。选轴先比较外钻深度、入口限制和窗口对齐；后续变更逐项携带实际 cycle 和条件依赖。没有把全部 Net 固定为 X/negative。', '',
        '## 原 T_DC/P/T 正权环', '',
        '原始真实数据复验得到 Y 上 `T_DC→P→T→T_DC`，每边 11.1 mm（闭合入口半径之和 + 既有 access gap）。首次针对性决策将 T_DC 主轴 X 改为 Y，原环消失；继续传播其他实际约束，最终整个原约束域求解成功。新的五面工作布局同样没有 process_gap。完整初始环、窗口成员、源 Cavity、每次工艺修改和最后的坐标域均保存。',
        '这不是把 planar 设为 false 后退出，也没有恢复 Catalog。原布局工艺重算后的实际钻孔仍有违规，测试明确要求它们继续被生产门禁拒绝。', '',
        '## 真实违规、局部修复与剩余 blocker', '',
        '- 旧固定几何的 source_protected 524.2981254966872 mm³、plug_cut 66.39930264676538 mm³ 均按原输入复验，依然被拒绝。后者明确是 R-e632b709-8 的已安装堵头与 R-e632b709-3 完整加工体相交；没有用两个堵头的包络替换实际关系。',
        '- 新布局的源安装检查通过，但七条 Net 的当前真实工艺仍不安全。具体失败对如下；完整孔参数和测量证据在 JSON/原始记录中。', '',
        '| Net | 实际失败项 |', '|---|---|']
    for n,rows in e['failures'].items():lines.append(f"| {n} | "+'; '.join(' / '.join(row) for row in rows)+' |')
    lines+=['', '仍未收口的机制：当前每 Net 仍用一个交汇点及所选外钻分支顺序。充分线性走廊域没有兑现所有第三方源保护、真实 Port 入口和每个分支的堵头/安装占用；生产筛查准确揭露了这一差异。局部入口/分离机制不能据此保证存在全网合法的多交汇安排。本轮未证明所支持的全部替代工艺均不可行，也未全面展开其他分支树。',
        '已验证通用局部入口修复会保持源和 OTHER Net 不变，真实 Exact/BRep/STEP 接纳；相关源改变时，全部窗口、相关 Net 和经过安装/切削扫掠区的第三方路线重新检查，未变化路线保留。失败缓存完整依赖防止旧第三方孔阻止新的合法事务。',
        '**复杂工程完整 Exact、BRep、STEP 没有执行，也没有制造通过声明。** 不能用符号无环或单 Net source-clear 代替连通性、直接开口或完整制造验收。', '',
        '## CAD UNKNOWN 的独立判断', '',
        '原固定最小几何被拆成六组真实正体积交集并保存 BRep。S0:w0/钻孔交集的质心截面约 0.031 s 返回；S1:w0/R-f42d38c6-1 的 323.9576661325285 mm³ 合法交集，在第一方向 Z 的实体/平面 Common 停滞。串行 Boolean、对原操作数先截面再求交、clean 后求交均在相同 8 s 隔离上限内未完成，保持 UNKNOWN。',
        '因此不能归因于未生成通道或缺少源定义；停滞属于已定位的原生 CAD 运算。容差/退化曲线敏感是尚未确认的解释，未更改容差、平面、直接接触规则或共享 flow.py。独立操作记录和 BRep 全部保留在 `opening/`。',
        '新位置/加工方向的共享刚体三 Net 见证通过生产 Exact（103/0/0、单实体、STEP 往返）；这证明该新几何可接纳，**不表示旧固定几何的原生运算问题已修复**。', '',
        '## 实测时间与验收', '',
        '| 工作阶段 | 调用数 | 秒 |', '|---|---:|---:|']
    for name in ('single.compile','single.net_associations','single.face_placement','single.process_decision','single.coordinates','single.materialization','single.precheck','single.source_envelopes'):
        value=e['timing']['operations'][name];lines.append(f"| {name} | {value['count']} | {value['seconds']:.6f} |")
    lines += ['', f"复杂快照本次私有进程总耗时 {current['execution']['elapsed_s']:.3f} s；完整加工 materialize 仅一次，499 次是实际线性约束传播，不是 499 个布局、钻孔 Catalog 或三维标签。工程定义/原生 CAD 前置运算次数见 JSON；未碰到执行上限。", '',
        f"旧负例一次 local repair：源侵入 {negatives['source']['timing']['operations']['single.local_repair']['seconds']:.3f} s；堵头 {negatives['plug']['timing']['operations']['single.local_repair']['seconds']:.3f} s。两者仍拒绝，不构造成功。生产默认 600/120/90 s 及取消/部分 Draft 保存机制未改。", '',
        '| 真实通用见证 | Exact PASS/WARNING/FAIL | BRep / STEP |', '|---|---|---|']
    for c in checks:
        label=next(label for token,label in [('directional_entry','仅入口局部修复'),('normal_chain','正常单工作两 Net'),('rigid_three','共享刚体三 Net'),('three_net_fixed','三方向 Net 工艺')] if token in c['path'])
        lines.append(f"| {label} | {c['counts']['PASS']}/{c['counts']['WARNING']}/{c['counts']['FAIL']} | valid / 1 solid / STEP PASS |")
    lines+=['', '聚焦验证覆盖五面真实加工、硬 Bottom/U/V/Rotation、二维面积定位、直接超图邻接、真实旧约束环、换面 Target、安装扫掠依赖、禁用入口、全部保留孔缓存依赖、原有真实 CAD 见证。Manual/API 验证覆盖 AI-origin Model 的 Preview/Optimize 不进入 AI 布局、部分 Draft 的 Save/Reload/Validate/Build、不隐式搜索，以及 Store 乐观 revision/API 守卫。',
        '最终成功的聚焦日志为 final-validation.xml、manual-api.xml、repair-dependencies.xml；早期失败和所有原始运行目录原样保留。未运行 T-10A、prove、广泛套件、浏览器、Vite、付费 AI 或新的完整复杂 Generate。', '',
        '## 隔离与交付', '',
        '13 个保护文件 SHA-256 前后完全一致，包含原始复杂 Design、原工程/AI 存档和 SQLite；清单在 JSON。',
        f"数据库 SHA-256：`{reference[str(ROOT/'data/pmc_engineering.db')]}`。",
        '共享 Router、CAD/Exact、工程安全阈值与项目 schema 未修改；自动面/位置/尺寸决策仅在显式新 Generate 的 WorkDesign 内执行。进入 Model 后仍按原有用户所有权工作。',
        '代码和本报告统一提交到既有分支。最终 commit、远端 HEAD、工作树及再核对哈希记录在 `output/runtime-checks/single-work-root-correction-20261014/delivery.json`，并由本次最终回复确认。', '',
        '机器可读交付：`docs/engineering/work-design-root-correction-evidence.json`；所有完整输入、计算表、路线和失败证据继续保留在本机运行目录。到此停止，不启动新的复杂 Generate。', '']
    (ROOT/'WORK_DESIGN_ROOT_CORRECTION_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(report='WORK_DESIGN_ROOT_CORRECTION_REPORT.md',evidence_bytes=path.stat().st_size,protected_files=len(reference),complex_manufacturing_ready=False)))


if __name__=='__main__':main()
