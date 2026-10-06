import {test} from 'node:test';
import assert from 'node:assert/strict';
import {relationKnowledgeUI} from '../web/relation-knowledge-ui.js';

class Node{
  constructor(tag,text=''){this.tag=tag;this.textContent=text||'';this.children=[];this.isConnected=true;}
  append(...rows){this.children.push(...rows);}
  replaceChildren(...rows){this.children=rows;}
}
const all=n=>[n,...n.children.flatMap(all)];
const words=n=>all(n).map(row=>row.textContent).join(' ');
const harness=api=>({element:(tag,text)=>new Node(tag,text),api,action(parent,text,fn){const node=new Node('button',text);node.onclick=fn;parent.append(node);return node;}});
const reference={cavity_name:'sc-08-02',verification_status:'CONFIRMED',confidence:.95,execution_eligible:false,resolution_status:'REFERENCE_ONLY_SUPPLEMENT',
  resolved_cavities:[],supplemental_cavities:[{display_name:'SC-08-02',unit:'inch',geometry_status:'NOT_COLLECTED',runtime_selectable:false}],
  evidence_text:'Official relation quotation',document_name:'Official catalogue',page_number:'2',source_url:'https://example.test/catalogue'};

test('relation-only Cartridge and supplement remain truthful read-only knowledge',async()=>{
  const root=new Node('div'),ctx=harness(async url=>url.endsWith('/technical')?{identity:{technical_record_present:false}}:{total:1,items:[reference]});
  await relationKnowledgeUI(ctx,root,'NEW',()=>true);
  assert.match(words(root),/No technical record in current technical package/);
  assert.match(words(root),/Geometry not collected/);
  assert.match(words(root),/Not selectable for machining \/ routing/);
  assert.match(words(root),/Official relation quotation/);
  assert.equal(all(root).some(row=>row.tag==='button'&&/Place|Bind|Use|Generate/.test(row.textContent)),false);
  const link=all(root).find(row=>row.tag==='a');assert.equal(link.href,'https://example.test/catalogue');assert.equal(link.rel,'noopener noreferrer');
});

test('existing technical values and normal compatibility remain independently visible',async()=>{
  const root=new Node('div'),ctx=harness(async url=>url.endsWith('/technical')?{identity:{technical_record_present:true},counts:{evidence:1},values:[{property:'rated_flow',normalized_value:30,normalized_unit:'L/min',original:{}}]}:{total:1,items:[{...reference,cavity_name:'A-1',execution_eligible:true,resolution_status:'RESOLVED',supplemental_cavities:[],resolved_cavities:[{name:'A-1',unit_system:'metric',usable:false}]}]});
  await relationKnowledgeUI(ctx,root,'OLD',()=>true);
  assert.match(words(root),/30 L\/min/);assert.match(words(root),/Execution-safe compatibility/);assert.match(words(root),/Geometry incomplete/);
  assert.equal(all(root).some(row=>row.tag==='button'&&/Place|Bind|Use/.test(row.textContent)),false);
});

test('unsafe source URLs and stale record responses are not rendered',async()=>{
  const root=new Node('div'),pending=[];let current=true;
  const ctx=harness(url=>new Promise(resolve=>pending.push({url,resolve})));
  const load=relationKnowledgeUI(ctx,root,'STALE',()=>current);current=false;
  for(const row of pending)row.resolve(row.url.endsWith('/technical')?{identity:{technical_record_present:false}}:{total:1,items:[reference]});
  await load;assert.doesNotMatch(words(root),/Official relation quotation|No technical record/);
  const unsafe=new Node('div');await relationKnowledgeUI(harness(async url=>url.endsWith('/technical')?{identity:{technical_record_present:false}}:{total:1,items:[{...reference,source_url:'javascript:alert(1)'}]}),unsafe,'C',()=>true);
  assert.equal(all(unsafe).some(row=>row.tag==='a'),false);
});
