import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {portSetup,customPort} from '../web/port-setup.js';
import {workflows} from '../web/workflows.js';

class Node {
  constructor(tag,text='',className=''){
    this.tagName=tag;this.textContent=text||'';this.className=className;this.children=[];
    this.value='';this.open=false;this.isConnected=true;this.disabled=false;
  }
  append(...children){for(const child of children){child.parentElement=this;child.isConnected=true;this.children.push(child);}}
  replaceChildren(...children){for(const child of this.children)child.isConnected=false;this.children=[];this.append(...children);}
  setAttribute(){}
  removeAttribute(){}
  showModal(){this.open=true;}
  close(){this.open=false;}
  querySelectorAll(selector){const found=[];for(const child of this.children){if(child.tagName===selector)found.push(child);found.push(...child.querySelectorAll(selector));}return found;}
}
const element=(tag,text,className)=>new Node(tag,text,className);
const all=node=>[node,...node.children.flatMap(all)];
const button=(node,label)=>all(node).find(item=>item.tagName==='button'&&item.textContent===label);
const labels=node=>all(node).filter(item=>item.tagName==='button').map(item=>item.textContent);
const field=(parent,label,value,onChange)=>{const input=element('input');input.label=label;input.value=value;input.onchange=()=>onChange(input.value);parent.append(input);return input;};
const action=(parent,label,fn)=>{const item=element('button',label);item.onclick=fn;parent.append(item);return item;};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const definition={id:'PORT_SOURCE',kind:'external-port',label:'#10 SAE',thread_note:'7/8-14 UNF',usable:true,zones:[{id:'P',offset_u:0,offset_v:0}]};
const forbidden=['Browse Standard Hydraulic Ports','Browse Reusable Custom Ports','View Definition','Create reusable custom external port'];

function portHarness(mode='standard'){
  const parent=element('div'),port=customPort(),calls=[];port.mode=mode;
  const api=async url=>{calls.push(url);if(url.startsWith('/api/catalog/standards'))return {items:['SAE_ORB']};if(url.startsWith('/api/catalog/definition'))return definition;return {items:[{id:definition.id,name:definition.label,thread_spec:definition.thread_note,unit_system:'inch',manufacturer:'PMC'}]};};
  const ctx={element,field,action,api,externalPortLibrary:()=>{throw Error('Library navigation was called');},viewExternalPort:()=>{throw Error('Library detail was called');},createCustomExternalPort:()=>{throw Error('Library management was called');}};
  const draw=()=>{parent.replaceChildren();portSetup(ctx,parent,port,'P',draw,'metric');};draw();
  return {parent,port,calls,draw};
}

test('port source modes expose inline selection only, including selected-definition state',async()=>{
  for(const mode of ['standard','reusable','oneoff']){
    const h=portHarness(mode);await flush();await flush();
    for(const text of forbidden)assert.equal(labels(h.parent).includes(text),false,`${mode}: ${text}`);
    if(mode==='oneoff'){assert.equal(button(h.parent,'Use for P'),undefined);continue;}
    assert.ok(button(h.parent,'Use for P'),`${mode} keeps inline use`);
    await button(h.parent,'Use for P').onclick();
    assert.equal(h.port.definition.id,definition.id);
    assert.ok(button(h.parent,'Change P definition'));
    for(const text of forbidden)assert.equal(labels(h.parent).includes(text),false,`selected ${mode}: ${text}`);
    button(h.parent,'Change P definition').onclick();
    assert.equal(h.port.definition,null);
    assert.ok(h.calls.some(url=>url.includes('status=usable')));
  }
});

test('cavity replacement picker stays local and uses only usable definitions',async()=>{
  const feature={id:'CV1',kind:'cavity',cavity_id:'OLD',interface_nets:{P:'P'}};
  const design={project_context:'inch',library:[],features:[feature],nets:[{id:'P',label:'P'}]};
  const nodes=Object.create(null),calls=[],replacements=[];
  const $=id=>nodes[id]??=element(id==='workflow-dialog'?'dialog':'div');
  const api=async url=>{calls.push(url);if(url.startsWith('/api/catalog/definition'))return {id:'NEW',kind:'cavity',label:'T-11A',usable:true,zones:[{id:'P'}]};if(url.startsWith('/api/catalog?'))return {items:[{id:'BAD',name:'Unusable',usable:false,active:true},{id:'NEW',name:'T-11A',usable:true,active:true,unit_system:'inch',manufacturer:'SUN',family:'T'}]};return {items:[]};};
  const ctx={$,element,field,action,api,post:async()=>{},get:()=>design,state:()=>({}),change:fn=>{fn();return true;},set:()=>{},newId:()=>'',select:()=>{},notice:()=>{},resolved:()=>null,adoptRoute:()=>{},replaceCavity:(f,id)=>replacements.push([f,id])};
  const handlers=workflows(ctx);
  handlers.changeCavityDefinition(feature);await flush();
  assert.equal($('workflow-title').textContent,'Change cavity definition · CV1');
  assert.ok(calls.some(url=>url.includes('kind=cavity')&&url.includes('unit=inch')&&url.includes('status=usable')));
  assert.equal(button($('workflow-content'),'View Definition'),undefined);
  assert.equal(button($('workflow-content'),'Duplicate as Custom'),undefined);
  assert.equal(button($('workflow-content'),'Open Engineering Library'),undefined);
  assert.equal(labels($('workflow-content')).filter(text=>text==='Use as replacement').length,1);
  await button($('workflow-content'),'Use as replacement').onclick();
  assert.deepEqual(replacements,[[feature,'NEW']]);
  assert.equal(design.library[0].id,'NEW');
  assert.equal($('workflow-dialog').open,false);
});

test('non-Library source has no record-management navigation bridges',()=>{
  const port=readFileSync(new URL('../web/port-setup.js',import.meta.url),'utf8');
  const main=readFileSync(new URL('../web/main.js',import.meta.url),'utf8');
  const flows=readFileSync(new URL('../web/workflows.js',import.meta.url),'utf8');
  for(const text of forbidden)assert.equal(port.includes(text),false,text);
  for(const text of ['Replace from Engineering Library','View Definition','Duplicate as Custom'])assert.equal(main.includes(text),false,text);
  for(const text of ['externalPortLibrary','viewExternalPort','createCustomExternalPort','replaceFromLibrary','duplicateDefinition'])assert.equal(flows.includes(text),false,text);
  assert.ok(main.includes('Change cavity definition'));
  assert.ok(main.includes('Assign compatible cartridge'));
});
