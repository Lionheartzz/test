import {test} from 'node:test';
import assert from 'node:assert/strict';
import {technicalKnowledgeUI,sourceLink,propertyLabel} from '../web/technical-knowledge-ui.js';
import {engineeringFactsUI} from '../web/engineering-facts-ui.js';

class Node{
  constructor(tag,text=''){this.tag=tag;this.textContent=text||'';this.children=[];}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
}
const all=node=>[node,...node.children.flatMap(all)];
const words=node=>all(node).map(row=>row.textContent).join(' ');
const button=(node,text)=>all(node).find(row=>row.tag==='button'&&row.textContent===text);
function setup(api=async()=>({items:[],total:0})){const root=new Node('div'),ctx={element:(tag,text)=>new Node(tag,text),
  action:(host,text,fn)=>{const n=new Node('button',text);n.onclick=fn;host.append(n);return n;},
  field:(host,label,value,fn)=>{const n=new Node('input',label);n.change=fn;host.append(n);return n;},api};return {root,ctx};}
const evidence=(id,property,value)=>({id,property,raw_value:value,raw_unit:'L/min',normalized_value:value,normalized_unit:'L/min',scope:'BASE_MODEL',scope_original:'BASE_MODEL',condition:'Nominal model condition',status:'EVIDENCE_PRESENT',evidence_class:'parameter',original:{evidence_id:id,source_title:'Official sheet',source_url:'https://example.test/source',page_number:'2',revision:'R2',confidence:.95,evidence_text:'Exact quotation'}});
const data=()=>({identity:{id:'C',full_part_number:'MODEL',base_model:'BASE',disposition:'PARTIAL_CONFIRMED',original:{}},
  values:[evidence('MAX','maximum_flow','30'),evidence('CAP','capacity','20')],values_total:2,counts:{evidence:21,sources:2,conflicts:0},field_status:[{field_group:'coil',status:'NOT_APPLICABLE'},{field_group:'seal',status:'NOT_REPORTED'}]});

test('resolved runtime facts and conditional references remain visibly different and read-only',()=>{
  const h=setup();let opened=0;
  engineeringFactsUI(h.ctx,h.root,{runtime_linked:true,facts:{
    maximum_working_pressure:{property:'maximum_working_pressure',value:350,unit:'bar',status:'SOURCE_BACKED'},
    rated_flow:{property:'rated_flow',value:null,status:'UNRESOLVED'}},
    references:[{property:'yield_strength',value:276,unit:'MPa',condition:'T6; Extrusion',status:'UNRESOLVED'}]},
    {evidence:()=>opened++});
  assert.match(words(h.root),/350 bar · Source-backed/);assert.match(words(h.root),/276 MPa · Reference only · T6; Extrusion/);
  assert.equal(all(h.root).some(n=>n.tag==='button'&&/Place|Bind|Use/.test(n.textContent)),false);
  button(h.root,'View technical evidence').onclick();assert.equal(opened,1);
});

test('Maximum Flow, Capacity, scopes and field gaps stay distinct; evidence is lazy and paginated',async()=>{
  const calls=[],h=setup(async url=>{calls.push(url);return {items:[evidence('EV','maximum_flow','30')],total:2};});
  technicalKnowledgeUI(h.ctx,h.root,data(),'/api/cartridges/C/technical',()=>true);
  assert.match(words(h.root),/Maximum Flow: 30/);assert.match(words(h.root),/Capacity: 20/);assert.match(words(h.root),/BASE_MODEL/);
  assert.match(words(h.root),/NOT_APPLICABLE/);assert.match(words(h.root),/NOT_REPORTED/);assert.equal(calls.length,0);
  assert.match(words(h.root),/Normalized: 30 L\/min/);
  await button(h.root,'Load technical evidence').onclick();await button(h.root,'More technical evidence').onclick();
  assert.match(calls[1],/offset=1/);assert.equal(all(h.root).filter(n=>n.tag==='a')[0].href,'https://example.test/source');
  assert.equal(all(h.root).some(n=>n.tag==='button'&&/Place|Bind|Use/.test(n.textContent)),false);
  assert.notEqual(propertyLabel('capacity'),propertyLabel('maximum_flow'));
});

test('Ambiguous and relation-only identities explain attribution without executable actions',()=>{
  for(const disposition of ['IDENTITY_AMBIGUOUS','RELATION_SOURCE_ONLY']){const h=setup(),d=data();d.identity.disposition=disposition;d.values=[];technicalKnowledgeUI(h.ctx,h.root,d,'/technical',()=>true);
    assert.match(words(h.root),disposition==='IDENTITY_AMBIGUOUS'?/not automatically inherited/:/not established in this research pass/);assert.equal(button(h.root,'Place'),undefined);}
});

test('Material treatment and research stock remain separate from engineering stock',async()=>{
  const h=setup(async()=>({items:[{availability:'LISTED_SIZE',original:{supplier:'Supplier',material:'C45',product_form:'Bar',width:'20',height:'20',length:'100',unit:'mm',notes:'Published listing only',source_url:'https://example.test/stock'}}],total:1})),d=data();
  d.identity.original={canonical_grade:'C45',standard:'EN',temper_condition:'Normalized',product_form:'Bar',aliases:['EN C45']};d.surface_treatments=[{treatment:'nitriding',status:'CONDITIONAL'}];d.engineering_stock=[];d.supplier_stock_count=1;
  technicalKnowledgeUI(h.ctx,h.root,d,'/api/materials/technical/MAT-C45',()=>true,{material:true});
  assert.match(words(h.root),/Engineering Stock/);assert.match(words(h.root),/Supplier \/ Research Stock Evidence/);assert.match(words(h.root),/CONDITIONAL/);assert.match(words(h.root),/No runtime stock/);
  await button(h.root,'Load supplier listings').onclick();assert.match(words(h.root),/LISTED_SIZE/);assert.match(words(h.root),/Published listing only/);
});

test('Conflict sides show source evidence and resolution without inventing a winner',async()=>{
  const h=setup(async()=>({items:[{property:'maximum_flow',conflict_type:'VALUE_CONFLICT',resolution:'OPEN',link_status:'LINKED',original:{evidence_a:'30',evidence_b:'40'},sides:{a:{total:1,items:[evidence('A','maximum_flow','30')]},b:{total:1,items:[evidence('B','maximum_flow','40')]}}}],total:1})),d=data();d.counts.conflicts=1;
  technicalKnowledgeUI(h.ctx,h.root,d,'/technical',()=>true);await button(h.root,'Load technical conflicts').onclick();assert.match(words(h.root),/Evidence A/);assert.match(words(h.root),/Evidence B/);assert.match(words(h.root),/OPEN/);assert.equal(words(h.root).includes('Explicit preferred evidence:'),false);
});

test('Stale evidence requests cannot modify a later page and local paths never become source links',async()=>{
  let release,current=true;const h=setup(()=>new Promise(resolve=>{release=resolve;}));technicalKnowledgeUI(h.ctx,h.root,data(),'/technical',()=>current);
  const pending=button(h.root,'Load technical evidence').onclick();current=false;release({items:[evidence('STALE','maximum_flow','999')],total:1});await pending;assert.equal(words(h.root).includes('999'),false);
  const host=new Node('div');for(const value of ['C:\\source.pdf','javascript:alert(1)','https:///','https:///example.test','https://example.test/one | https://example.test/two','file:///source.pdf'])sourceLink(h.ctx,host,value);assert.equal(host.children.length,0);
});
