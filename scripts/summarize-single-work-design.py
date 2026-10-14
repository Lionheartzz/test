"""Publish a compact truthful report from saved evidence; no solver/CAD calls."""
import collections
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/runtime-checks/single-work-20261014'
OLD=ROOT/'output/runtime-checks/engineering-planner-20261014'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    cases={n:read(RUN/n/'result.json') for n in ('facts','precheck','source','plug')}
    for r in cases.values():
        assert r['execution']['reason']=='COMPLETED'
        assert all(sha(ROOT/p)==h for p,h in r['code_hashes'].items()),'Code changed after bounded snapshot verification'
    facts=cases['facts']['result']['evidence'];pre=cases['precheck']['result']['evidence']
    labels={c['placement_id']:c['label'] for c in cases['facts']['result']['design']['schematic_intent']['components']}
    table=facts['initial_calculation']
    for f in table['features']:f['label']=labels.get(f['feature'],f['feature'])
    by_feature={f['feature']:f for f in table['features']}
    for s in table['spacing']:
        a,b=[by_feature[k]['extents']['origin'] for k in s['features']]
        s.update(actual_center_distance_mm=math.dist(a,b),actual_axis_distance_mm=b[s['axis']]-a[s['axis']],
            satisfies_selected_separation=b[s['axis']]-a[s['axis']]+1e-6>=s['required'])
    protected=read(OLD/'protected-reference.json');after={p:sha(Path(p)) for p in protected}
    assert protected==after,'Protected file changed'
    oldrow=read(next((OLD/'complex-frozen-final').rglob('layouts/000.json')))
    pools={n:dict(source_clear=oldrow['assessment']['pools'][n]['source_clear'],
        retained_samples=[dict(variant=o['variant'],failures=o['failures']) for o in oldrow['assessment']['pools'][n]['rejected_samples']])
        for n in ('MA','MB','P','T')}
    summaries={}
    for name,r in cases.items():
        e=r['result']['evidence']
        first=next((d for d in e['decisions'] if d['kind']=='PRODUCTION_MACHINING_PRECHECK'),{})
        summaries[name]=dict(status=r['result']['status'],source=r['source'],execution=r['execution'],
            timing=e['timing'],cache=e['cache_lookups'],initial_failures=first.get('failures'),
            initial_measurements=first.get('measurements',[]) if name in ('source','plug') else [],
            final_failures=e['failures'],failure_counts={n:dict(collections.Counter(f[0] for f in fs)) for n,fs in e['failures'].items()},
            repair_records=[d for d in e['decisions'] if d['kind'].startswith('LOCAL_')],
            global_layout_queue=e['global_layout_queue'],catalog_searches=e['catalog_searches'],deep_labels=e['deep_labels'],
            raw_evidence=str((RUN/name/'result.json').relative_to(ROOT)))
    accepted={}
    for parent in ('release-focused','final-engineering'):
        for p in (RUN/parent).rglob('acceptance.json'):
            x=read(p);accepted[p.parent.parent.name]=dict(case=p.parent.parent.name,path=str(p.relative_to(ROOT)),sha256=sha(p),
                status=x['status'],counts=(x.get('validation') or {}).get('counts'),topology=x.get('topology'),step=x.get('step'))
    accepted=list(accepted.values())
    unknown=read(next((RUN/'final-focused').rglob('bounded-exact.json')))
    tests=[]
    for name in ('final-focused','release-focused','final-engineering','final-gate','final-isolation','occupied-final','axial-metadata','contour-correction'):
        t=ET.parse(RUN/(name+'.xml')).getroot()[0];tests.append(dict(evidence=name,**t.attrib))
    data=dict(baseline='767cbc2c6d476d632bbb3d6c54057ed33c6b4651',scope='ONE_WORK_DESIGN_BOUNDED_SNAPSHOTS',
        outcome='CONTROL_FLOW_CORRECTED_COMPLEX_ENGINEERING_UNACCEPTED',manufacturing_ready=False,
        full_complex_generate_run=False,code_hashes=cases['precheck']['code_hashes'],
        initial_calculation=table,engineering_facts=pre['engineering_plan']['facts'],net_hypergraph=pre['engineering_plan']['net_hypergraph'],
        process_gap=pre['process_gap'],processes=pre['selected_processes'],
        junctions=pre['junctions'],operations=pre['operations'],drillings=pre['actual_drillings'],cases=summaries,
        previous_failed_pools=pools,previous_screen_seconds=oldrow['screen_seconds'],
        current_actual_cad_acceptance=accepted,
        shared_rigid_cad=dict(status='UNKNOWN_NATIVE_OPENING_CALCULATION_LIMIT' if unknown['result'] is None else unknown['result']['status'],
            execution=unknown['execution'],evidence=unknown['evidence'],manufacturing_accepted=False,
            note='Safe time-limit classification is not a passed CAD witness; historical accepted shared-rigid evidence remains preserved'),
        tests=tests,protected_before=protected,protected_after=after,protected_unchanged=True,
        publication_identity='output/runtime-checks/single-work-20261014/delivery.json')
    target=ROOT/'docs/engineering/single-layout-engineering-evidence.json'
    target.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    lines=['# 单工作设计工程规划与加工闭环整改',
        '', '基线 `767cbc2c6d476d632bbb3d6c54057ed33c6b4651`；分支 `codex/sqlite-domain-reset`。',
        '', '**控制流已整改；复杂工程仍未达到完整设计验收。** 本次没有运行完整复杂 Generate。',
        '提交与远端身份在发布后写入 `output/runtime-checks/single-work-20261014/delivery.json`，最终答复同时给出真实 SHA；提交内不写自引用 SHA。',
        '', '## 生产调用链', '',
        '修改前：Generate → plan_new → 多布局 optimize（48）→ Controller 返回已拒绝工艺 → screen → Session.prepare → 全 Net Catalog / 深搜。',
        '修改后：Generate → plan_new → optimize → 一个 WorkDesign / EngineeringPlan → 工艺约束求坐标 → 完整生产钻孔 → production machining precheck → 同一设计的测量修复事务 → LocalAdmission → 完整方案才进入 Exact/BRep/STEP。',
        '正常路径不调用 initial_candidates、pack_topology、pop_diverse、screen 或 Session.prepare；旧工具显式保留。layout_limit 兼容参数不再控制布局。',
        '源码：`single_design.py` 主控制；`joint_layout.py::optimize` 调用和接纳；`engineering_decisions.py` 清除拒绝工艺外泄；`route_catalog.py` 对显式工艺设禁止目录扩展门禁。',
        '', '## 真实复杂输入：初始工程计算', '',
        f"源布局为 **{' × '.join(f'{v:.6f}' for v in table['dimensions'])} mm**，源安装门禁通过。尺寸同时保留了轴向安装堵头与源停深的必要空间；工艺域仍有矛盾，不证明全部钻孔走廊可制造。",
        '同面圆形间距使用 Ri+Rj+Gij；非圆形使用旋转后的切削和实际边界投影，并以生产 CAD 安装/边界实体复核。压力壁厚、流量和工具沿用生产逻辑，未知值留为 UNKNOWN。',
        '相对面仅在实际投影重叠时叠加深度；通用见证分别算出 42 mm（分离）与 82 mm（重叠）。移动遇到对面源时，根据真实背壁计算尺寸增长，不按固定比例放大。',
        '', '| 元件 | 面 / 旋转 | U / V (mm) | 实际加工深度 / 壁厚 (mm) | 面内投影支持 |',
        '|---|---|---|---|---|']
    for f in table['features']:
        e=f['extents'];lines.append(f"| {f['label']} | {f['face']} / {f['rotation']:g}° | {f['u']:.6f} / {f['v']:.6f} | {e['depth']:.6f} / {e['wall']:.6f} | {e['projected_supports']} |")
    lines+=['', '元件优先顺序、Net 超图耦合分组、全部同面中心距公式/数值/元件对、每个元件的约束和各 Block 维度的有向约束，完整存于伴随 JSON 的 `initial_calculation`。不能从此表推断未检查的阀体高度或压力资格。',
        '', '## 每条 Net 的工艺计划', '',
        '以下是当前工艺意图和已实例化加工孔，不是合格走廊。交汇坐标在工艺约束矛盾时仅用于诊断；不送往昂贵搜索。完整外表面入口、深度、钻尖、闭合 ID、啮合和包络均在 JSON `drillings/operations`。',
        '', '| Net | 主轴 / 层轴 / 入口 | 诊断交汇坐标 (mm) | 孔数 | 前检结果 |', '|---|---|---|---|---|']
    axes='XYZ'
    for n,p in pre['selected_processes'].items():
        layer=axes[p['layer_axis']] if p['layer_axis'] is not None else '—'
        lines.append(f"| {n} | {axes[p['spine_axis']]} / {layer} / {p['entry']} | {tuple(round(v,6) for v in pre['junctions'][n])} | {len(pre['actual_drillings'].get(n,[]))} | {dict(collections.Counter(f[0] for f in pre['failures'].get(n,[])))} |")
    lines+=['', '## 两项已知违规及局部修复', '',
        '| 原证据 | 同输入生产复现 | 局部事务 | 最终状态 |', '|---|---|---|---|',
        '| 源保护侵入 | CV_6bbcdb6cce3a4c816cb3 ↔ R-702e7749-4；524.2981254966872 mm³ | 重建不同入口并用完整源/堵头/第三方检查；测量分离不等式回传源和走廊变量 | 新工艺仍违规，已回退，原违规保留 |',
        '| 堵头/切削 | R-e632b709-3 ↔ R-e632b709-8；66.39930264676538 mm³ | 先确认哪一侧实际安装堵头侵入另一侧完整切削体，再建占用/切削分离约束；不是比较两个堵头 | 新工艺仍违规，已回退，原违规保留 |',
        '', '每个事务的原规则、轴、完整边界、壁厚/间隙、所需距离、受影响 Net、重建后的全部失败及回退结果见 JSON `cases.*.repair_records`。局部改入口成功的通用见证只重建 N，另一网 OTHER 的实际孔和全部源位置不变。',
        '源移动会扩展到共享刚体全部窗口及扫掠区域相交的第三方路线；Block 变化使全部受尺寸影响的孔失效并重新加工。冻结/非拥有变量始终受域约束，不通过 origin 授权。',
        '', '## 尚存的具体工程 blocker', '',
        '1. 当前统一逃逸顺序要求 T_DC→P、P→T、T→T_DC 在同一 Y 方向各相隔 11.1 mm，形成正权环。已切换受矛盾影响的直接/平面工艺，仍没有满足这一工艺域的共同坐标。此为当前单交汇/统一逃逸层表达缺口，不是物理无解，也不是搜索额度结论。',
        '2. 已修复另一项 Planner/Router 不一致：孤立源轴向可用，不代表只按源深度计算的 Block 可容纳安装堵头。现在厚度包含源停深偏移、真实啮合及完整圆柱半径；AI 显式轴向工艺传递实际绑定的闭合定义，默认 Manual 调用不变。当前 P 已实例化 9 个真实孔；仍被 source_protected、installation_access、plug_cut 拒绝。具体规则和实体在 `cases.precheck.final_failures.P`。',
        '3. 对这些已拒绝工艺，入口改变也产生新的真实违规，分离域仍矛盾；未找到可提交的修复。因此保留源合法 Draft，不转入下一布局、全网目录或深搜。',
        '4. 共享刚体三网见证在本次独立进程内停于生产 hydraulic.opening 运算，上限安全停止，分类 UNKNOWN。没有出现可用于证明物理违规的结果；没有把该检查写作 CAD PASS。旧共享刚体接纳记录保留，当前独立进程重复性仍是 CAD 运算 blocker。',
        '', '旧布局的 MA/MB/P 样例同时有 source_protected、installation_access、plug_cut；T 原计划只有 plug_cut。旧目录只保存少量拒绝样例，不能据此宣称所有合法入口均已检查；摘要和原证据路径都在 JSON `previous_failed_pools`。',
        '', '## 时间、缓存与真实工作量', '',
        '| 有界任务 | 含启动耗时 (s) | 编译 | 坐标求解 | 实体生成 | 前检 | 局部修复 |', '|---|---|---|---|---|---|---|']
    for n,r in summaries.items():
        ops=r['timing']['operations'];value=lambda k:ops.get(k,{}).get('seconds',0)
        lines.append(f"| {n} | {r['execution']['elapsed_s']:.3f} | {value('single.compile'):.3f} | {value('single.coordinates'):.3f} | {value('single.materialization'):.3f} | {value('single.precheck'):.3f} | {value('single.local_repair'):.3f} |")
    lines+=['', '表中总耗时为 supervisor 统计的子进程生命周期，外层诊断 CLI 的 Python 启动另计。阶段时间为包围时间，父子阶段和 Boolean 计时可能重叠，不能相加作独占 CPU 时间。Router 的真实工艺实例化计入实体生成；目录调用、深搜标签、全局布局队列均为 0。CAD Boolean/几何/源包络次数和时间、CPU、缓存字典命中/未命中见 JSON；字典命中不是“节省的 CAD 次数”。',
        f"旧第一布局完整目录筛查 {oldrow['screen_seconds']:.3f} s；本次一个主设计前检 {summaries['precheck']['timing']['operations']['single.precheck']['seconds']:.3f} s。两者布局及工作量不同，不能称为等价工作提速或完整设计性能通过。安全上限仍是 600/120/90 s，诊断用更短 25/20/2 s；明确拒绝不会继续消耗通用搜索。",
        '', '## 真实 CAD 和隔离验证', '']
    for r in accepted:lines.append(f"- {r['case']}: {r['status']}，{r['counts']}，BRep {r['topology']}，STEP {r['step']['status']}。")
    lines+=['- 源轴向停深见证、直接交汇不足后的实际轴线修复，也用生产 Exact 验证；未放宽直接接触规则。',
        '- 正常调用链检查以禁止入口探针证明没有进入旧布局/目录/三维搜索；CAD 结果由真实生产接口生成。',
        '- 部分路线用既有 Save Draft 持久化并在新进程重载；Validate/Build 对尚未完成路线保持明确拒绝，未隐式搜索或移动源。普通 Save 的原有拒绝语义保留。',
        '- Manual Preview / Optimize、Store/API 版本冲突与路径守卫、原有取消及时间上限均有聚焦检查；默认 Router 操作记录开启/关闭生成相同几何。',
        f'- 13 个保护文件哈希前后一致，包括 SQLite、原始复杂源和原项目/AI 任务；数据库 SHA-256 `{after[str(ROOT/"data/pmc_engineering.db")]}`。完整清单在 JSON。',
        '- 未运行 T-10A、prove、全量套件、浏览器、Vite、付费 AI 或新的完整复杂 Generate。',
        '', '机器可读证据：`docs/engineering/single-layout-engineering-evidence.json`；全部原始运行证据继续保留在 `output/runtime-checks/single-work-20261014/`。',
        '', '**交付不包含复杂工程制造通过声明。原始工程和 Library 保持不变；没有继续开始下一轮长 Generate。**', '']
    (ROOT/'SINGLE_LAYOUT_ENGINEERING_CLOSURE_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(report='SINGLE_LAYOUT_ENGINEERING_CLOSURE_REPORT.md',json_bytes=target.stat().st_size,
        protected_unchanged=True,manufacturing_ready=False,full_complex_generate=False)))


if __name__=='__main__':main()
