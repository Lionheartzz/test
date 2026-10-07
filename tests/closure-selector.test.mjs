import {test} from 'node:test';
import assert from 'node:assert/strict';
import {closureSelector} from '../web/closure-selector.js';
class Node{
  constructor(tag,text=''){this.tag=tag;this.textContent=text||'';this.children=[];this.isConnected=true;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
}
test('compatible closure control shows friendly model and applies source engagement',async()=>{
  const root=new Node('div'),feature={diameter:8,depth:60,plug_length:8,closure_definition_id:null};let input;
  const row={id:'source-choice',display_name:'SFC KOENIG MB 600-090',engagement_mm:10,envelope:{diameter_mm:9.1,height_mm:0}};
  const ctx={element:(tag,text)=>new Node(tag,text),api:async()=>({items:[row]}),change:fn=>fn(),
    field:(p,label,value,fn,options)=>{assert.equal(label,'Closure / Plug');assert.equal(options['source-choice'],row.display_name);input={choose:fn};return input;}};
  await closureSelector(ctx,root,feature,'metric',()=>true);input.choose(row.id);
  assert.equal(feature.closure_definition_id,row.id);assert.equal(feature.plug_length,10);assert.equal(feature.diameter,8);assert.equal(feature.clearance_height,0);
  input.choose('');assert.equal(feature.closure_definition_id,null);assert.equal(feature.clearance_height,20);
});
test('stale closure response never creates a control',async()=>{
  const root=new Node('div');let rendered=false;
  await closureSelector({element:(tag,text)=>new Node(tag,text),api:async()=>({items:[]}),field:()=>{rendered=true;}},root,{diameter:8,depth:60},'inch',()=>false);
  assert.equal(rendered,false);
});
