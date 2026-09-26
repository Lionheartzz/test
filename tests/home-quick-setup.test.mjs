import {test} from 'node:test';
import assert from 'node:assert/strict';
import {renderHome} from '../web/home-view.js';
import {prefillGuidedBlock} from '../web/project-library.js';
import {guided} from '../web/guided.js';

class Node {
  constructor(tag,text='',className=''){
    this.tagName=tag;this.textContent=text||'';this.className=className;
    this.children=[];this.dataset={};this.attributes={};this.value='';this.isConnected=true;
    this.classList={add(){}};
  }
  append(...children){for(const child of children){child.parentElement=this;this.children.push(child);}}
  prepend(child){child.parentElement=this;this.children.unshift(child);}
  replaceChildren(...children){this.children=[];this.append(...children);}
  setAttribute(name,value){this.attributes[name]=String(value);}
  getAttribute(name){return this.attributes[name]??null;}
  removeAttribute(name){delete this.attributes[name];}
  querySelectorAll(selector){const tags=selector.split(',').map(value=>value.trim());const found=[];const visit=node=>{for(const child of node.children){if(tags.includes(child.tagName))found.push(child);visit(child);}};visit(this);return found;}
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
