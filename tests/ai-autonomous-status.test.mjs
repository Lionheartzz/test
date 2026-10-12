import test from 'node:test';
import assert from 'node:assert/strict';
import {aiGeneration} from '../web/ai-generation.js';

class Element {
  constructor(tag,text=''){this.tagName=tag;this.textContent=text||'';this.children=[];this.classList={add(){}};this.open=true;}
  append(...items){this.children.push(...items);}setAttribute(){}close(){this.open=false;}
}
const all=n=>[n,...n.children.flatMap(all)];

test('unresolved AI layout needs review and opens Model only through explicit handoff',async()=>{
  const content=new Element('div'),dialog=new Element('dialog'),title=new Element('h2'),opened=[];
  const design={features:[],nets:[]};
  const ctx={$:id=>({'workflow-content':content,'workflow-dialog':dialog,'workflow-title':title}[id]),
    element:(tag,text)=>new Element(tag,text),action:(parent,text,fn)=>{const b=new Element('button',text);b.onclick=fn;parent.append(b);return b;},
    post:async(url,body)=>{assert.equal(url,'/api/import-project');return {design:body,engineering:{definitions:{},threads:{}}};},
    newProject:current=>{opened.push(current);return true;},notice(){}};
  const ui=aiGeneration(ctx,{open:text=>title.textContent=text,back(){},session:()=>({}),refreshTask(){},watchJob(){}});
  ui.showPacket({status:'incomplete_draft',design,message:'Joint layout/routing remains unresolved.',task_id:'a',id:'b',
    validation:null,attempts:[{index:0,error:'Exact source connectivity rejected; not verified.',counts:null,geometry_failures:null}]});
  assert.ok(all(content).some(n=>n.textContent==='Generation needs review'));
  assert.ok(all(content).some(n=>n.textContent.includes('Exact source connectivity rejected')));
  assert.ok(!all(content).some(n=>n.textContent==='Your editable manifold draft'));
  assert.equal(opened.length,0);
  await all(content).find(n=>n.textContent==='Open draft in Manifold Studio').onclick();
  assert.deepEqual(opened,[design]);assert.equal(dialog.open,false);
});
