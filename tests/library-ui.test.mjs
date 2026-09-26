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
