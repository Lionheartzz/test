import {test} from 'node:test';
import assert from 'node:assert/strict';
import {featureLabel,returnNetToAutomatic,smartAlign} from '../web/kinematics.js';
import {displayExternalPortName,displayMemberName,displayIdentity} from '../web/presentation.js';
import {nextExpectedInterface,renameExpectedInterface,filterThreadChoices} from '../web/workflows.js';
import {aiGeneration,inspectGeneratedDraft} from '../web/ai-generation.js';
import {hydrateDesign} from '../web/domain.js';

test('generated route labels hide hash ids and keep a deterministic cavity/net alias',()=>{
  const design={features:[
    {id:'CV1',kind:'cavity'},
    {id:'R-5c62e091-1',kind:'drilling',route_net:'P',connects_to:['CV1:port1']},
    {id:'R-5c62e091-2',kind:'drilling',route_net:'P',connects_to:['R-5c62e091-1']},
  ]};
  assert.equal(featureLabel(design.features[1],design),'CV1-P1');
  assert.equal(featureLabel(design.features[2],design),'CV1-P2');
});

test('returning a refined route to automatic removes only owned geometry and preserves construction access',()=>{
  const design={block:{length:100,width:100,height:100},nets:[{id:'P',routing:'manual',routing_variant:'xyz:nearest:direct',construction_access:[{id:'ACCESS_P',face:'top',fraction:.5}]},{id:'T',routing:'automatic'}],features:[
    {id:'CV1',kind:'cavity',connects_to:[]},
    {id:'P-FROZEN',kind:'drilling',frozen_net:'P',connects_to:['CV1:port1']},
    {id:'T-ROUTE',kind:'drilling',route_net:'T',connects_to:['P-FROZEN']},
  ]};
  returnNetToAutomatic(design,'P');
  assert.deepEqual(design.features.map(f=>f.id),['CV1','T-ROUTE']);
  assert.deepEqual(design.features[1].connects_to,[]);
  assert.equal(design.nets[0].routing,'automatic');assert.equal(design.nets[0].routing_variant,null);assert.deepEqual(design.nets[0].construction_access,[{id:'ACCESS_P',face:'top',fraction:.5}]);
  assert.equal(design.nets[1].routing,'automatic');
});

test('opaque external-port identities use deterministic engineering labels only in presentation',()=>{
  const design={nets:[{id:'P',label:'P'}],features:[
    {id:'PORT_later',kind:'port',circuit:'P',face:'front',u:30,v:20},
    {id:'PORT_first',kind:'port',circuit:'P',face:'front',u:10,v:20},
    {id:'CV1',kind:'cavity',interface_nets:{port1:'P'}},
  ]};
  assert.equal(displayExternalPortName(design.features[0],design),'P2');
  assert.equal(displayExternalPortName(design.features[1],design),'P1');
  assert.equal(displayMemberName(design,'CV1:port1'),'CV1-P');
  assert.equal(displayMemberName(design,'PORT_first'),'P1');
  assert.equal(design.features[1].id,'PORT_first');
});

test('net IDs and multi-cavity route branches use stable presentation names',()=>{
  const design={nets:[{id:'NET_P',label:'P'}],features:[
    {id:'CV1',kind:'cavity',interface_nets:{port1:'NET_P'}},
    {id:'CV2',kind:'cavity',interface_nets:{port1:'NET_P'}},
    {id:'R-hash-1',kind:'drilling',route_net:'NET_P',connects_to:['CV1:port1']},
    {id:'R-hash-2',kind:'drilling',route_net:'NET_P',connects_to:['CV1:port1','R-hash-1']},
    {id:'R-hash-3',kind:'drilling',route_net:'NET_P',connects_to:['CV2:port1']},
    {id:'R-hash-4',kind:'drilling',route_net:'NET_P',connects_to:['R-hash-1','R-hash-3']},
  ]};
  assert.equal(displayIdentity(design,'NET_P'),'P');
  assert.equal(featureLabel(design.features[2],design),'CV1-P1');
  assert.equal(featureLabel(design.features[3],design),'CV1-P2');
  assert.equal(featureLabel(design.features[4],design),'CV2-P1');
  assert.equal(featureLabel(design.features[5],design),'P1');
});

test('manual schematic intent uses bound cavity interface IDs and keeps mappings when renamed',()=>{
  const placement={id:'CV1',kind:'cavity',interface_nets:{P:'P',T:'T',A:'A',B:'B'}};
  const component={expected_interfaces:[],interface_nets:{}};
  for(let i=0;i<4;i++)component.expected_interfaces.push(nextExpectedInterface(component,placement));
  assert.deepEqual(component.expected_interfaces,['P','T','A','B']);
  const legacy={expected_interfaces:['port1'],interface_nets:{port1:'P'},interface_dispositions:{port1:'connected'}};
  renameExpectedInterface(legacy,'port1','P');
  assert.deepEqual(legacy,{expected_interfaces:['P'],interface_nets:{P:'P'},interface_dispositions:{P:'connected'}});
});

test('AI draft handoff resolves SQLite definitions before entering the Viewer',async()=>{
  const packet={design:{features:[{kind:'cavity',cavity_id:'CAV_A'},{id:'MH1',kind:'mounting',thread_definition_id:'THREAD_M10'}]}},calls=[];
  const post=async(url,design)=>{calls.push(['inspect',url,design]);return {design,engineering:{definitions:{CAV_A:{id:'CAV_A',cutting_primitives:[{}]}},threads:{THREAD_M10:{id:'THREAD_M10',display_name:'M10x1.5-6H',tap_diameter_mm:8}}}};};
  const handoff=await inspectGeneratedDraft(packet,post);calls.push(['open',handoff]);
  assert.equal(calls[0][1],'/api/import-project');
  assert.equal(handoff.definitions.CAV_A.id,'CAV_A');
  const opened=hydrateDesign(handoff.design,handoff.definitions,handoff.threads);
  assert.equal(opened.threads.find(row=>row.id===opened.features[1].thread_definition_id).display_name,'M10x1.5-6H');
  assert.equal(opened.threads[0].tap_diameter_mm,8);
  assert.deepEqual(calls.map(row=>row[0]),['inspect','open']);
});

test('AI generation renders a fresh plan with provisional and threaded mounting state',async()=>{
  const actions=[],fields=[];
  const element=(tag,text='',className='')=>({tag,textContent:text,className,children:[],open:false,
    classList:{add(){}},append(...children){this.children.push(...children);},setAttribute(){},querySelectorAll(){return [];}});
  const content=element('div'),dialog={open:true},title={textContent:''},error={textContent:''};
  const $=id=>({'workflow-content':content,'workflow-dialog':dialog,'workflow-title':title,'workflow-error':error})[id];
  const field=(parent,label,value,onChange)=>{fields.push({label,value,onChange});const input=element('input');parent.append(input);return input;};
  const action=(parent,label,callback)=>{actions.push({label,callback});const button=element('button',label);parent.append(button);return button;};
  let submitted;
  const post=async(_url,body)=>{submitted=structuredClone(body.options);return {ready:false,blocked:['Choose port geometry'],components:[],
    external_ports:[{id:'EXT_P',label:'P',specification:'',definition:null,standard:null,provisional:Object.hasOwn(body.options.provisional_ports,'EXT_P')}],
    mounting_requirements:['M10x1.5 at engineer-entered positions'],mounting_holes:[],ports:[],nets:[],dispositions:[]};};
  const api=async()=>({families:['BSPP','Metric','UNC'],items:[{id:'THREAD_M10',normalized_family:'Metric',unit_system:'metric',display_name:'M10x1.5-6H'}]});
  const task={id:'TASK',revision:'REV',inputs:{project_context:'metric'}},run={id:'RUN',status:'completed',provider:{id:'mock',model:'fixture',is_mock:true}};
  const generator=aiGeneration({$,element,field,action,api,post},{open:label=>{title.textContent=label;content.children=[];},back(){},
    session:()=>({task,run,dirty:false}),refreshTask(){},watchJob(){}});
  await generator.prepare();
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(submitted.provisional_ports,{});
  assert.deepEqual(submitted.threaded_mounting_holes,[]);
  assert.equal(submitted.mounting_decision,'');
  assert.equal(fields.find(row=>row.label==='Thread standard / family')?.value,'Metric');
  assert.equal(fields.find(row=>row.label==='Native standard')?.value,'');
  assert.ok(actions.some(row=>row.label==='Choose One-off Custom Straight Bore · P'));
  actions.find(row=>row.label==='Choose One-off Custom Straight Bore · P').callback();
  await new Promise(resolve=>setImmediate(resolve));
  assert.ok(Object.hasOwn(submitted.provisional_ports,'EXT_P'));
  assert.ok(fields.some(row=>row.label==='Provisional straight-bore decision · P'));
  task.inputs.project_context='inch';run.id='RUN_INCH';
  await generator.prepare();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(fields.filter(row=>row.label==='Thread standard / family').at(-1)?.value,'UNC');
});

test('Smart Align uses the SQLite external-port hydraulic window without duplicated depth',()=>{
  const definition={id:'PORT_DEF',stages:[{diameter:12}],clearance_diameter:16,boundaries:[],zones:[{id:'port1',start:10,end:20}]};
  const port={id:'PORT_DB',kind:'port',face:'left',u:30,v:25,port_definition_id:'PORT_DEF',circuit:'P',suppressed:false};
  const target={id:'DRILL',kind:'drilling',face:'top',u:14.5,v:30,diameter:8,depth:20,clearance_diameter:8,plugged:false,suppressed:false};
  const design={block:{length:100,width:80,height:60},library:[definition],features:[target,port]};
  assert.deepEqual(smartAlign(target,design,target.u,target.v,2,[port]).values,[15,30]);
});

test('thread selector groups by engineering family and defaults to mixed native units',()=>{
  const rows=[{id:'M10',normalized_family:'Metric',unit_system:'metric',display_name:'M10x1.5-6H',nominal_size:'M10',pitch_tpi:'1.5',thread_class:'6H'},
    {id:'UNC',normalized_family:'UNC',unit_system:'inch',display_name:'3/8-16 UNC-2B',nominal_size:'3/8',pitch_tpi:'16',thread_class:'2B'}];
  assert.deepEqual(filterThreadChoices(rows,'UNC').map(row=>row.id),['UNC']);
  assert.deepEqual(filterThreadChoices(rows,'Metric','').map(row=>row.id),['M10']);
  assert.deepEqual(filterThreadChoices(rows,'UNC','metric'),[]);
});
