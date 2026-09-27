import {test} from 'node:test';
import assert from 'node:assert/strict';
import {libraryUI} from '../web/library-ui.js';

// Minimal DOM-like harness: this regression is about request ownership, not layout.
class Node {constructor(tag,text='',cls=''){this.tagName=tag;this.textContent=text||'';this.className=cls;this.children=[];this.value='';this.classList={add(){}};}append(...xs){this.children.push(...xs);}replaceChildren(...xs){this.children=[...xs];this.textContent=xs.map(x=>x.textContent||'').join('');}setAttribute(){}querySelectorAll(){return [];} }
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
for(const hasDraft of [true,false])test(`Engineering Library renders and searches ${hasDraft?'with a draft':'from Home without a draft'}`,async()=>{
  const nodes={content:new Node('div'),error:new Node('div')},calls=[];
  const ctx={get:()=>hasDraft?{project_context:''}:null,$:(id)=>id==='workflow-content'?nodes.content:nodes.error,
    element:(tag,text,cls)=>new Node(tag,text,cls),field:(parent,label,value,onChange)=>{const input=new Node('input');input.value=value;input.onchange=()=>onChange(input.value);parent.append(input);if(label==='Search cavity')nodes.search=input;return input;},
    action:(parent,label,fn)=>{const b=new Node('button',label);b.onclick=fn;parent.append(b);return b;},post:async()=>{},
    api:async url=>{calls.push(url);const q=new URL('http://local'+url).searchParams.get('q');return {total:1,items:[{id:q?'SECOND':'FIRST',name:q?'T-10A':'Initial cavity',family:'QA',manufacturer:'PMC',unit_system:'metric',thread_spec:'',usable:1,unusable_reason:'',active:1}]};}};
  const open=()=>nodes.content.replaceChildren(),ui=libraryUI(ctx,{open,insert:()=>{}});await ui();
  const list=nodes.content.children.find(x=>x.className==='library-list');assert.equal(list.children[1].children[0].textContent,'Initial cavity');
  assert.equal(!!list.children[1].children.find(x=>x.textContent==='Place Cavity').disabled,!hasDraft);
  nodes.search.value='T-10A';nodes.search.oninput();await sleep(220);
  assert.equal(calls.length,2);assert.match(calls[1],/q=T-10A/);assert.equal(list.children[1].children[0].textContent,'T-10A');
});

test('Cartridge Lookup separates execution evidence from review-only evidence',async()=>{
  const nodes={content:new Node('div'),error:new Node('div')},calls=[];
  const item=(id,eligible)=>({relation_id:id,cavity_family:'Maker',cavity_name:'A-1',
    execution_eligible:eligible,verification_status:eligible?'CONFIRMED':'PROBABLE',
    confidence:eligible?.95:.70,resolution_status:'RESOLVED',resolution_detail:{reason:''},
    resolved_cavities:[],document_name:'Catalogue',document_revision:'R1',page_number:'7',
    evidence_text:'A-1 stated in source',source_url:'https://example.test/catalogue'});
  const ctx={get:()=>null,$:id=>id==='workflow-content'?nodes.content:nodes.error,
    element:(tag,value,cls)=>new Node(tag,value,cls),field:(parent)=>{const input=new Node('input');parent.append(input);return input;},
    action:(parent,label,fn)=>{const button=new Node('button',label);button.onclick=fn;parent.append(button);return button;},
    post:async()=>{},api:async url=>{calls.push(url);if(url.startsWith('/api/catalog?'))return {total:0,items:[]};
      if(url.startsWith('/api/cartridges?'))return {total:1,items:[{id:'cart_1',manufacturer:'Maker',model:'MODEL',function:''}]};
      if(url.startsWith('/api/knowledge/cartridges/'))return {total:2,items:[item('REL_SAFE',true),item('REL_REVIEW',false)]};
      throw Error('Unexpected '+url);}};
  const open=()=>nodes.content.replaceChildren();await libraryUI(ctx,{open,insert:()=>{}})();
  const lookup=nodes.content.children.flatMap(x=>[x,...x.children]).find(x=>x.textContent==='Cartridge Lookup');await lookup.onclick();
  const list=nodes.content.children.find(x=>x.className==='library-list');
  await list.children[1].children.find(x=>x.textContent==='Review cavity evidence').onclick();
  const sections=nodes.content.children.filter(x=>x.className==='library-list');
  assert.equal(sections.length,2);assert.equal(sections[0].children[0].children[1].textContent.startsWith('EXECUTION SAFE'),true);
  assert.equal(sections[1].children[0].children[1].textContent.startsWith('EVIDENCE ONLY'),true);
  assert.ok(calls.some(x=>x.includes('/api/knowledge/cartridges/cart_1/cavities')));
});
