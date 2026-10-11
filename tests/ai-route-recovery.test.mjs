import test from 'node:test';
import assert from 'node:assert/strict';
import {aiGeneration,inspectGeneratedDraft} from '../web/ai-generation.js';
class Element{
  constructor(tag,text=''){this.tagName=tag;this.textContent=text||'';this.children=[];this.classList={add:()=>{}};this.open=true;}
  append(...nodes){this.children.push(...nodes);}setAttribute(){}close(){this.open=false;}
}
const all=n=>[n,...n.children.flatMap(all)];
function harness(post){
  const content=new Element('div'),dialog=new Element('dialog'),title=new Element('h2'),error=new Element('p');
  const ctx={$:id=>({'workflow-content':content,'workflow-dialog':dialog,'workflow-title':title,'workflow-error':error}[id]),
    element:(tag,text)=>new Element(tag,text),action:(parent,text,fn)=>{const b=new Element('button',text);b.onclick=fn;parent.append(b);return b;},
    post,newProject:()=>true,notice:()=>{}};
  const ui=aiGeneration(ctx,{open:message=>{title.textContent=message;content.children=[];},back:()=>{},session:()=>({}),refreshTask:()=>{},watchJob:()=>{}});
  return {ui,content,error};
}
const packet=()=>({id:'g',task_id:'t',status:'draft',message:'Historical draft',attempts:[],
  layout_planning:{scope:'AI_GENERATION_ONLY',selected:{status:'ANALYTIC_UNVALIDATED'}},
  design:{features:[],nets:[{id:'N',routing_variant:'branch_0_50_50_50:xyz:nearest'}]}});

test('recovery is explicit and opening/import never silently strips user variants',async()=>{
  let requests=0;const old=packet(),snapshot=structuredClone(old);
  const {ui,content}=harness(async(url,body)=>{requests++;assert.ok(url.endsWith('/recover-analytic-routes'));
    assert.deepEqual(body,old.design);return {design:{features:[],nets:[{id:'N',routing_variant:null}]},message:'Recovered copy'};});
  ui.showPacket(old);assert.equal(requests,0);
  await all(content).find(n=>n.textContent==='Recover automatic route search').onclick();
  assert.equal(requests,1);assert.deepEqual(old,snapshot);
  assert.ok(all(content).find(n=>n.tagName==='a').href.includes('release_analytic_samples=true'));
  const explicit={design:{features:[],nets:[{id:'N',routing_variant:'xyz:nearest:direct'}]}};
  const handoff=await inspectGeneratedDraft(explicit,async(_,body)=>({design:body,engineering:{}}));
  assert.equal(handoff.design.nets[0].routing_variant,'xyz:nearest:direct');
});

test('a stale recovery response cannot replace another displayed draft',async()=>{
  let complete;const {ui,content}=harness(()=>new Promise(resolve=>complete=resolve));
  ui.showPacket(packet());const pending=all(content).find(n=>n.textContent==='Recover automatic route search').onclick();
  ui.showPacket({...packet(),id:'other',message:'Newer draft'});
  complete({design:{features:[],nets:[]},message:'Stale recovered copy'});await pending;
  assert.ok(all(content).some(n=>n.textContent==='Newer draft'));
  assert.ok(!all(content).some(n=>n.textContent==='Stale recovered copy'));
});
