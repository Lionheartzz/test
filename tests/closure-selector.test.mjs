import {test} from 'node:test';
import assert from 'node:assert/strict';
import {closureSelector} from '../web/closure-selector.js';
import {createPreviewQueue} from '../web/preview-queue.js';
class Node{
  constructor(tag,text=''){this.tag=tag;this.textContent=text||'';this.children=[];this.isConnected=true;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
}
test('compatible closure control shows friendly model and applies source engagement',async()=>{
  const root=new Node('div'),feature={id:'R1',diameter:8,depth:60,plug_length:8,closure_definition_id:null};let input;
  const row={id:'source-choice',display_name:'SFC KOENIG MB 600-090',engagement_mm:10,envelope:{diameter_mm:9.1,height_mm:0}};
  const ctx={element:(tag,text)=>new Node(tag,text),api:async()=>({items:[row]}),change:(fn,edit)=>{assert.deepEqual(edit,{kind:'closure',feature_ids:['R1']});fn();},
    field:(p,label,value,fn,options)=>{assert.equal(label,'Closure / Plug');assert.equal(options['source-choice'],row.display_name);input={choose:fn};return input;}};
  await closureSelector(ctx,root,feature,'metric',()=>true);input.choose(row.id);
  assert.equal(feature.closure_definition_id,row.id);assert.equal(feature.plug_length,10);assert.equal(feature.diameter,8);assert.equal(feature.clearance_height,0);
  input.choose('');assert.equal(feature.closure_definition_id,null);assert.equal(feature.clearance_height,20);
  assert.equal(feature.closure_selection_mode,'manual');
});
test('stale closure response never creates a control',async()=>{
  const root=new Node('div');let rendered=false;
  await closureSelector({element:(tag,text)=>new Node(tag,text),api:async()=>({items:[]}),field:()=>{rendered=true;}},root,{diameter:8,depth:60},'inch',()=>false);
  assert.equal(rendered,false);
});

test('legacy closure alias displays its canonical generic selection without editing the project',async()=>{
  const root=new Node('div'),feature={diameter:8,depth:60,closure_definition_id:'old-product-id'};let displayed;
  await closureSelector({element:(tag,text)=>new Node(tag,text),api:async()=>({items:[{id:'generic-id',display_name:'Expander Plug Ø9',aliases:['old-product-id']}]}),
    field:(p,label,value)=>{displayed=value;return {};},change:()=>assert.fail('Browsing must not edit')},root,feature,'metric',()=>true);
  assert.equal(displayed,'generic-id');assert.equal(feature.closure_definition_id,'old-product-id');
  assert.ok(!root.children[0].children.some(n=>n.textContent==='Selected closure is not compatible.'));
});

test('switching generic closure sends changed geometry inputs to the exact preview pipeline',async()=>{
  const root=new Node('div'),feature={diameter:8,depth:60,plug_length:8,closure_definition_id:null};let input;
  const rows=[{id:'entry-9',display_name:'Expander Plug Ø9',engagement_mm:10,envelope:{diameter_mm:9.1,height_mm:0}},
    {id:'entry-10',display_name:'Expander Plug Ø10',engagement_mm:11.3,envelope:{diameter_mm:10.1,height_mm:0}}];
  const exact=[];
  const queue=createPreviewQueue({delay:1,exactDelay:1,post:async(url,design)=>{if(url==='/api/preview-solid')exact.push(design);return {};},
    onFast:()=>{},onExact:()=>{},onStatus:()=>{},onError:error=>{throw error;}});
  try{
    const ctx={element:(tag,text)=>new Node(tag,text),api:async()=>({items:rows}),
      change:fn=>{fn();queue.schedule({features:[structuredClone(feature)]});},field:(p,label,value,fn)=>input={choose:fn}};
    await closureSelector(ctx,root,feature,'metric',()=>true);
    input.choose(rows[0].id);await new Promise(r=>setTimeout(r,40));
    input.choose(rows[1].id);await new Promise(r=>setTimeout(r,40));
    assert.equal(exact.length,2);
    assert.deepEqual(exact.map(d=>d.features[0].closure_definition_id),['entry-9','entry-10']);
    assert.deepEqual(exact.map(d=>d.features[0].plug_length),[10,11.3]);
    assert.ok(exact.every(d=>d.features[0].diameter===8));
  }finally{queue.cancel();}
});
