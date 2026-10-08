import test from 'node:test';
import assert from 'node:assert/strict';
import {aiGeneration,inspectGeneratedDraft} from '../web/ai-generation.js';
class Element{
  constructor(tag,text=''){this.tagName=tag;this.textContent=text||'';this.children=[];this.classList={add:()=>{}};this.open=true;}
  append(...items){this.children.push(...items);}setAttribute(){}close(){this.open=false;}
}
const all=n=>[n,...n.children.flatMap(all)];
test('cancelled or failed generation can hand off its unvalidated authored draft to normal Studio',async()=>{
  for(const status of ['incomplete_draft','cancelled']){
    const content=new Element('div'),dialog=new Element('dialog'),title=new Element('h2'),error=new Element('p');
    const source={features:[{id:'CV1',cavity_id:'real-source-id'}],nets:[{id:'P',route_state:'unresolved'}]},calls=[],opened=[];
    const ctx={$:id=>({'workflow-content':content,'workflow-dialog':dialog,'workflow-title':title,'workflow-error':error}[id]),
      element:(tag,text)=>new Element(tag,text),action:(parent,text,fn)=>{const button=new Element('button',text);button.onclick=fn;parent.append(button);return button;},
      post:async(url,design)=>{calls.push([url,design]);return {design,engineering:{definitions:{},threads:{}}};},
      newProject:(design)=>{opened.push(design);return true;},notice:()=>{}};
    const ui=aiGeneration(ctx,{open:message=>title.textContent=message,back:()=>{},session:()=>({}),refreshTask:()=>{},watchJob:()=>{}});
    ui.showPacket({status,design:source,message:'CAD calculation interrupted; draft retained.',task_id:'a',id:'b',attempts:[{index:0,error:'interrupted'}]});
    assert.ok(all(content).some(n=>n.textContent.includes('Unvalidated authored draft retained')));
    const open=all(content).find(n=>n.textContent==='Open draft in Manifold Studio');assert.ok(open);
    await open.onclick();assert.equal(calls[0][0],'/api/import-project');assert.deepEqual(opened[0],source);
    assert.equal(opened[0].nets[0].route_state,'unresolved');assert.equal(dialog.open,false);
  }
});
test('handoff uses import inspection, never marks an AI packet as authoritative validation',async()=>{
  const source={features:[],nets:[]};
  const result=await inspectGeneratedDraft({design:source},async(url,body)=>{
    assert.equal(url,'/api/import-project');assert.equal(body,source);return {design:body,engineering:{definitions:{D:{id:'D'}},threads:{}}};
  });
  assert.equal(result.design,source);assert.ok(result.definitions.D);assert.equal('validation' in result,false);
});
