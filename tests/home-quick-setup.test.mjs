import {test} from 'node:test';
import assert from 'node:assert/strict';
import {renderHome} from '../web/home-view.js';
import {prefillGuidedBlock} from '../web/project-library.js';
import {guided} from '../web/guided.js';

class Node {
  constructor(tag,text='',className=''){
    this.tagName=tag;this.textContent=text||'';this.className=className;
    this.children=[];this.dataset={};this.attributes={};this.value='';this.disabled=false;this.isConnected=true;this.scrollTop=0;
    this.classList={add(){}};
  }
  append(...children){for(const child of children){child.parentElement=this;this.children.push(child);}}
  prepend(child){child.parentElement=this;this.children.unshift(child);}
  replaceChildren(...children){this.children=[];this.append(...children);}
  setAttribute(name,value){this.attributes[name]=String(value);}
  getAttribute(name){return this.attributes[name]??null;}
  removeAttribute(name){delete this.attributes[name];}
  querySelectorAll(selector){const tags=selector.split(',').map(value=>value.trim());const found=[];const visit=node=>{for(const child of node.children){if(tags.includes(child.tagName))found.push(child);visit(child);}};visit(this);return found;}
  querySelector(selector){const matches=node=>selector.startsWith('#')?node.id===selector.slice(1):node.tagName===selector;const visit=node=>{if(matches(node))return node;for(const child of node.children){const found=visit(child);if(found)return found;}return null;};return visit(this);}
  getBoundingClientRect(){return {top:this.top??0};}
  focus(options){this.focusOptions=options;globalThis.document.activeElement=this;}
  get firstElementChild(){return this.children[0]??null;}
  get valueAsNumber(){return Number(this.value);}
  get selectedOptions(){return this.children.filter(child=>child.tagName==='option'&&child.value===this.value);}
  dispatchEvent(){this.onchange?.();}
  setCustomValidity(){}
  reportValidity(){return true;}
  close(){this.open=false;}
  showModal(){this.open=true;}
}

const material={id:'MAT_TEST',display_name:'Source backed test material',active:true};
const element=(tag,text,className)=>new Node(tag,text,className);
const find=(parent,tag,text)=>parent.querySelectorAll(tag).find(node=>node.textContent===text);
const field=(parent,label,value,onChange,options=null,numeric=false)=>{
  const input=element(options?'select':'input');input.setAttribute('aria-label',label);input.value=value;
  input.onchange=()=>onChange(numeric?input.valueAsNumber:input.value);parent.append(input);return input;
};

function homeSidebar(hasDraft){
  const previous=globalThis.document;globalThis.document={createElementNS:(_,tag)=>new Node(tag),activeElement:null};
  const launched=[],returned=[];let apiCalls=0;
  const root=renderHome({element,action:(parent,label,callback)=>{const button=element('button',label);button.onclick=callback;parent.append(button);return button;},
    api:async path=>{apiCalls++;return path==='/api/materials'?{items:[]}:path==='/api/health'?{service:'pmc-manifold',network:{mode:'local'}}:{schema_version:3};},
    launch:id=>launched.push(id),hasProject:()=>hasDraft,returnToDraft:()=>returned.push(true),startSetup:()=>{}});
  const nav=label=>root.layout.querySelectorAll('button').find(node=>node.getAttribute('aria-label')===label);
  return {root,nav,launched,returned,apiCalls:()=>apiCalls,restore:()=>{globalThis.document=previous;}};
}

test('Home Projects jumps to the existing project heading without changing Home or setup state',()=>{
  const h=homeSidebar(false);
  try{
    assert.ok(h.nav('Projects'));
    assert.deepEqual(['Home','Projects','New Manifold','Model','Drawing','AI Design'],
      h.root.layout.querySelector('nav').querySelectorAll('button').slice(0,6).map(node=>node.getAttribute('aria-label')));
    const title=element('h2','Archived projects');h.root.projects.append(title);
    const name=h.root.layout.querySelectorAll('input').find(node=>node.value==='New manifold');name.value='Unfinished setup';
    const calls=h.apiCalls(),projects=h.root.projects,content=projects.parentElement;
    projects.top=336;content.top=48;
    h.nav('Projects').onclick();
    assert.equal(projects.id,'home-projects');
    assert.equal(content.scrollTop,272);
    assert.equal(globalThis.document.activeElement,title);
    assert.equal(title.tabIndex,-1);
    assert.deepEqual(title.focusOptions,{preventScroll:true});
    assert.equal(h.nav('Projects').getAttribute('aria-current'),'location');
    assert.equal(h.nav('Home').getAttribute('aria-current'),null);
    assert.equal(title.textContent,'Archived projects');
    assert.equal(name.value,'Unfinished setup');
    assert.equal(h.apiCalls(),calls);
    assert.deepEqual(h.launched,[]);
    assert.equal(projects.parentElement.className,'home-content');
    h.nav('Home').onclick();
    assert.equal(content.scrollTop,0);
    assert.equal(h.nav('Home').getAttribute('aria-current'),'page');
    assert.equal(h.nav('Projects').getAttribute('aria-current'),null);
  }finally{h.restore();}
});

test('Home sidebar separates New Manifold, Model, Drawing, AI and Engineering actions',()=>{
  const empty=homeSidebar(false);
  try{
    assert.equal(empty.nav('Model').disabled,true);
    assert.equal(empty.nav('Model').title,'Model · Open or create a manifold first');
    empty.nav('Model').onclick();
    assert.deepEqual(empty.launched,[]);
    assert.deepEqual(empty.returned,[]);
    empty.nav('New Manifold').onclick();
    empty.nav('AI Design').onclick();
    empty.nav('Engineering Library').onclick();
    assert.deepEqual(empty.launched,['project-new','ai-design-open','library-open']);
    assert.equal(empty.nav('Drawing').disabled,true);
  }finally{empty.restore();}
  const current=homeSidebar(true);
  try{
    assert.equal(current.nav('Model').disabled,false);
    current.nav('Model').onclick();
    assert.deepEqual(current.returned,[true]);
    assert.deepEqual(current.launched,[]);
    assert.equal(current.nav('Drawing').disabled,false);
    current.nav('Drawing').onclick();
    assert.deepEqual(current.launched,['drawings-open']);
  }finally{current.restore();}
});

async function homeSelection(){
  const previous=globalThis.document;globalThis.document={createElementNS:(_,tag)=>new Node(tag)};
  try{
    let submitted;
    const root=renderHome({element,action:(parent,label,callback)=>{const button=element('button',label);button.onclick=callback;parent.append(button);return button;},
      api:async path=>path==='/api/materials'?{items:[material]}:path==='/api/health'?{service:'pmc-manifold',network:{mode:'local'}}:{schema_version:2},
      launch:()=>{},hasProject:()=>false,returnToDraft:()=>{},startSetup:values=>submitted=values});
    await Promise.resolve();
    const name=root.layout.querySelectorAll('input').find(node=>node.value==='New manifold');
    const select=root.layout.querySelectorAll('select').find(node=>node.getAttribute('aria-label')==='Material');
    assert.equal(name.maxLength,120);
    const option=select.children.find(node=>node.value===material.id);
    assert.equal(option.textContent,material.display_name);
    assert.equal(option.dataset.name,material.display_name);
    select.value=material.id;
    root.layout.querySelectorAll('form')[0].onsubmit({preventDefault(){}});
    assert.deepEqual(submitted.material,{id:material.id,name:material.display_name});
    return submitted;
  }finally{globalThis.document=previous;}
}

async function createFromGuided(values,changeMaterial=false){
  const nodes={
    'project-new':element('button'),
    'workflow-content':element('div'),
    'workflow-dialog':element('dialog'),
    'workflow-title':element('h2'),
    'workflow-error':element('div'),
  };
  const $=id=>nodes[id];let created;
  const open=title=>{nodes['workflow-title'].textContent=title;nodes['workflow-content'].replaceChildren();nodes['workflow-error'].textContent='';nodes['workflow-dialog'].showModal();};
  guided({$,element,field,action:(parent,label,callback)=>{const button=element('button',label);button.onclick=callback;parent.append(button);return button;},
    post:async(path,design)=>{assert.equal(path,'/api/check-design');return design;},
    api:async()=>({items:[]}),notice:()=>{},newProject:design=>{created=design;return true;}},open);
  nodes['project-new'].onclick();
  prefillGuidedBlock($,values);
  const content=nodes['workflow-content'];
  const materialInput=content.querySelectorAll('input').find(node=>node.getAttribute('aria-label')==='Block material / grade');
  assert.equal(materialInput.value,material.display_name);
  assert.equal(materialInput.dataset.materialId,material.id);
  if(changeMaterial){materialInput.value='Custom material';materialInput.dispatchEvent(new Event('change'));}
  find(content,'button','Next · Nets and ports').onclick();
  const nets=content.querySelectorAll('input').find(node=>node.getAttribute('aria-label')==='Net IDs (comma separated)');
  nets.value='P';nets.dispatchEvent(new Event('change'));
  const portCount=content.querySelectorAll('input').find(node=>node.getAttribute('aria-label')==='P · External port quantity');
  portCount.value='0';portCount.dispatchEvent(new Event('change'));
  find(content,'button','Next · Cartridges and cavities').onclick();
  find(content,'button','Continue without cavities').onclick();
  find(content,'button','Next · Review').onclick();
  await find(content,'button','Create editable draft').onclick();
  assert.equal(nodes['workflow-error'].textContent,'');
  assert.ok(created,'Guided did not create a draft');
  return created;
}

test('Home material option carries SQLite id and name; project name limit matches schema',async()=>{
  await homeSelection();
});

test('Home Quick Setup preserves material identity through the existing five-step Guided flow',async()=>{
  const draft=await createFromGuided(await homeSelection());
  assert.equal(draft.block.material,material.display_name);
  assert.equal(draft.block.material_id,material.id);
  assert.equal(draft.block.stock_id,undefined);
  assert.equal(draft.block.stock_dimensions,undefined);
  assert.equal(draft.block.machining_allowance,undefined);
});

test('customized Guided material text clears the previous SQLite material identity',async()=>{
  const draft=await createFromGuided(await homeSelection(),true);
  assert.equal(draft.block.material,'Custom material');
  assert.equal(draft.block.material_id,undefined);
});
