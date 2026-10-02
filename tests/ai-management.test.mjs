import {test} from 'node:test';
import assert from 'node:assert/strict';
import {aiDesign} from '../web/ai-design.js';
import {analysisStatus,documentSummary} from '../web/ai-management.js';

class Node{
  constructor(tag,text='',cls=''){this.tagName=tag;this.textContent=text||'';this.className=cls;this.children=[];this.attrs={};this.classList={add:()=>{}};this.disabled=false;this.value='';this.open=false;}
  append(...n){this.children.push(...n);}setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k];}
  replaceChildren(...n){this.children=n;this.textContent='';}
  querySelectorAll(){return all(this).filter(n=>['button','input','select','textarea'].includes(n.tagName));}
  querySelector(q){return all(this).find(n=>n.className?.split(' ').includes(q.slice(1)));}
}
const all=n=>[n,...n.children.flatMap(all)],words=n=>all(n).map(x=>x.textContent).join(' ');
function harness(){
  const nodes={content:new Node('div'),dialog:new Node('dialog'),title:new Node('h2'),error:new Node('p'),trigger:new Node('button')},calls=[],fields=[];
  const record={id:'a'.repeat(32),revision:'b'.repeat(64),inputs:{title:'Valve analysis',documents:[{asset:{name:'valve.png'}}],engineering_requirements:'',project_context:'metric'},latest_run:null};
  const rows=[{id:record.id,title:record.inputs.title,documents:1,document_names:['valve.png'],generated_draft_count:1,updated_at:'2026-10-02T04:00:00Z',latest_run:{status:'completed',id:'c'.repeat(32)}}];
  const h={nodes,calls,fields,rows,current:null};
  const ctx={get:()=>null,state:()=>({}),$:id=>({'workflow-content':nodes.content,'workflow-dialog':nodes.dialog,'workflow-title':nodes.title,'workflow-error':nodes.error,'ai-design-open':nodes.trigger}[id]),
    element:(tag,text,cls)=>new Node(tag,text,cls),
    field:(parent,label,value,onChange)=>{const n=new Node('input');n.value=value;n.onchange=()=>onChange(n.value);parent.append(n);fields.push({label,node:n});return n;},
    action:(parent,label,fn)=>{const n=new Node('button',label);n.onclick=fn;parent.append(n);return n;},post:async(...args)=>{calls.push(args);return h.savedResponse||record;},
    api:async(url,options)=>{calls.push([url,options]);if(options?.method==='DELETE'){rows.splice(0);return {deleted:true};}
      if(url==='/api/assets')return h.assetResponse;
      if(url==='/api/ai-design/tasks')return rows;if(url==='/api/ai-design/providers')return [];if(url==='/api/ai-design/jobs/current')return h.current;
      if(url.includes('/api/ai-design/jobs/'))return {status:'completed'};
      if(url==='/api/ai-design/tasks/'+record.id)return record;throw Error('Unexpected '+url);},};
  aiDesign(ctx,title=>{nodes.title.textContent=title;nodes.dialog.open=true;nodes.content.replaceChildren();});
  h.open=()=>nodes.trigger.onclick();h.button=label=>all(nodes.content).find(n=>n.tagName==='button'&&n.textContent===label);h.field=label=>fields.filter(f=>f.label===label).at(-1).node;
  return h;
}

test('management status separates analysis lifecycle, generation jobs and document summaries',()=>{
  const row={id:'A',documents:3,document_names:['first.pdf','b.png','c.png'],latest_run:{status:'completed'}};
  assert.equal(documentSummary(row),'3 documents · first.pdf +2');
  assert.equal(analysisStatus(row,{task_id:'A',operation:'generate',status:'running'}),'Completed');
  assert.equal(analysisStatus(row,{task_id:'A',operation:'analyze',status:'queued'}),'Running');
  assert.equal(analysisStatus({...row,stale:true}),'Inputs changed · re-analysis required');
  assert.equal(analysisStatus({...row,latest_attempt:{status:'failed',error:'INVALID_STRUCTURED_OUTPUT'}}),'Failed · INVALID_STRUCTURED_OUTPUT');
  assert.equal(analysisStatus({}),'Not analyzed');
});

test('top-level always opens Management; dirty editor resumes without saving or discarding',async()=>{
  const old=globalThis.document;globalThis.document={createTextNode:text=>new Node('text',text)};
  try{const h=harness();await h.open();assert.equal(h.nodes.title.textContent,'AI Design · Management');
    assert.match(words(h.nodes.content),/valve.png.*Analysis: Completed.*Generated drafts: 1.*Updated:/);
    assert(h.button('New AI Design')&&h.button('Provider Settings'));await h.button('Open').onclick();
    const title=h.field('Analysis title');title.value='Changed but unsaved';title.onchange();
    await h.open();assert.equal(h.nodes.title.textContent,'AI Design · Management');assert(h.button('Resume'));
    assert(!h.calls.some(([url,options])=>options?.method==='POST'));
    await h.button('Resume').onclick();assert.equal(h.field('Analysis title').value,'Changed but unsaved');
    await h.button('Back to AI Design Management').onclick();assert.equal(h.nodes.title.textContent,'AI Design · Management');
    await h.button('New AI Design').onclick();assert.equal(h.field('Analysis title').value,'New hydraulic analysis');
    await h.open();assert.equal(all(h.nodes.content).filter(n=>n.tagName==='h3'&&n.textContent==='Unsaved AI Design').length,2);
  }finally{globalThis.document=old;}
});

test('explicit Delete confirms workspace scope and a generation job blocks Delete',async()=>{
  const old=globalThis.confirm,messages=[];globalThis.confirm=text=>{messages.push(text);return true;};
  try{const h=harness();await h.open();await h.button('Delete').onclick();assert.match(messages[0],/Saved Manifold Projects are not affected/);
    assert(h.calls.some(([url,options])=>url.endsWith('a'.repeat(32))&&options?.method==='DELETE'));
    const running=harness();running.current={task_id:'a'.repeat(32),operation:'generate',status:'running',id:'c'.repeat(32)};await running.open();
    assert(running.button('Delete').disabled);assert.match(words(running.nodes.content),/Analysis: Completed.*Draft generation: Running/);
  }finally{globalThis.confirm=old;}
});

test('a pending upload completed in Management remains available through Resume',async()=>{
  const old=globalThis.document;globalThis.document={createTextNode:text=>new Node('text',text)};
  try{const h=harness();await h.open();await h.button('Open').onclick();
    let complete;h.assetResponse=new Promise(resolve=>complete=resolve);
    const file=all(h.nodes.content).find(n=>n.tagName==='input'&&n.type==='file');file.files=[{type:'image/png',size:32,name:'new.png'}];const uploading=file.onchange();
    await h.open();complete({sha256:'f'.repeat(64),name:'new.png',media_type:'image/png',size:32});await uploading;
    assert.equal(h.nodes.title.textContent,'AI Design · Management');await h.button('Resume').onclick();assert.match(words(h.nodes.content),/new.png/);
  }finally{globalThis.document=old;}
});

test('explicit Save finishing after top-level navigation refreshes Management without hijacking it',async()=>{
  const old=globalThis.document;globalThis.document={createTextNode:text=>new Node('text',text)};
  try{const h=harness();await h.open();await h.button('Open').onclick();h.field('Analysis title').value='Saved title';h.field('Analysis title').onchange();
    let complete;h.savedResponse=new Promise(resolve=>complete=resolve);const saving=h.button('Save inputs').onclick();await h.open();
    complete({id:'a'.repeat(32),revision:'b'.repeat(64),inputs:{title:'Saved title',documents:[],engineering_requirements:'',project_context:'metric'}});await saving;
    assert.equal(h.nodes.title.textContent,'AI Design · Management');assert(!h.button('Resume'));
  }finally{globalThis.document=old;}
});
