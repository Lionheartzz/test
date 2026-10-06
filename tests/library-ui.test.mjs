import {test} from 'node:test';
import assert from 'node:assert/strict';
import {libraryUI} from '../web/library-ui.js';

class Node {
  constructor(tag,text='',cls=''){
    this.tagName=tag;this.textContent=text||'';this.className=cls;this.children=[];
    this.value='';this.disabled=false;this.scrollTop=0;this.classList={add:()=>{}};
  }
  append(...children){this.children.push(...children);}
  prepend(...children){this.children.unshift(...children);}
  replaceChildren(...children){this.children=[...children];this.textContent='';}
  setAttribute(){}
  querySelectorAll(){return [];}
}

test('Material direct entry returns to category without reopening its detail',async()=>{
  const calls=[],h=harness(async url=>{calls.push(url);
    if(url==='/api/materials/technical/MAT')return {identity:{id:'MAT',full_part_number:'6061',material_id:'runtime',disposition:'PARTIAL',original:{}},
      counts:{evidence:0,sources:0,conflicts:0},values:[],values_total:0,field_status:[],surface_treatments:[],engineering_stock:[]};
    if(url==='/api/materials')return {items:[{id:'runtime',technical_identity_id:'MAT',display_name:'6061 T6',stock:[],active:true}]};
    if(url==='/api/engineering-library/materials/runtime')return {groups:[]};
    if(url==='/api/materials/technical')return {items:[]};
    throw Error('Unexpected '+url);
  });
  await h.ui({entryCategory:'materials',recordId:'MAT',readOnly:true});
  await button(h.nodes.content,'Back to Materials & Stock').onclick();
  assert.equal(h.titles.at(-1),'Engineering Library / Materials & Stock');
  assert(h.field('Search'));
  assert.equal(calls.filter(url=>url.endsWith('/technical/MAT')).length,0);
});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const all=node=>[node,...node.children.flatMap(all)];
const button=(node,label)=>all(node).find(item=>item.tagName==='button'&&item.textContent===label);
const words=node=>all(node).map(item=>item.textContent).join(' ');

function harness(api,{draft=null}={}){
  const nodes={content:new Node('div'),dialog:new Node('dialog'),error:new Node('p')};
  const fields=[];
  const ctx={
    get:()=>draft,
    $:id=>({'workflow-content':nodes.content,'workflow-dialog':nodes.dialog,'workflow-error':nodes.error}[id]),
    element:(tag,text,cls)=>new Node(tag,text,cls),
    field:(parent,label,value,onChange)=>{const input=new Node('input');input.value=value;input.onchange=()=>onChange(input.value);parent.append(input);fields.push({label,input});return input;},
    action:(parent,label,fn)=>{const item=new Node('button',label);item.onclick=fn;parent.append(item);return item;},
    api,post:async()=>{},
  };
  const titles=[];
  const ui=libraryUI(ctx,{open:title=>{titles.push(title);nodes.content.replaceChildren();},insert:()=>{}});
  return {ui,nodes,fields,titles,field:label=>fields.filter(item=>item.label===label).at(-1)?.input};
}

test('Engineering Library opens a category dashboard and one failed count stays local to its card',async()=>{
  const calls=[];
  const h=harness(async url=>{
    calls.push(url);
    if(url==='/api/engineering-library/categories'||url.startsWith('/api/closures'))throw Error('offline');
    if(url.startsWith('/api/materials'))return {items:[{id:'MAT'}]};
    if(url.startsWith('/api/tools'))return {items:[],total:2};
    return {items:[],total:7};
  });
  await h.ui();await sleep(5);
  assert.equal(h.titles.at(-1),'Engineering Library');
  const grid=all(h.nodes.content).find(node=>node.className==='library-category-grid');
  assert.equal(grid.children.length,20);
  for(const name of ['Cavities','Cartridges','External Ports','Threads','Materials & Stock','Tooling','Closures & Plugs','Machining Modifiers'])assert.ok(words(grid).includes(name));
  const failed=grid.children.find(card=>words(card).includes('Closures & Plugs'));
  assert.match(words(failed),/Count unavailable/);
  assert.match(words(grid.children[0]),/7 definitions/);
  assert.ok(calls.some(url=>url.startsWith('/api/closures')));
});

test('Explicit cavity selection enters Cavities directly; projectless browse disables placement',async()=>{
  const h=harness(async url=>{
    if(url.startsWith('/api/catalog?'))return {total:1,items:[{id:'CAV_A',name:'Cavity A',family:'QA',manufacturer:'PMC',unit_system:'metric',thread_spec:'',usable:1,active:1}]};
    throw Error('Unexpected '+url);
  });
  await h.ui({entryCategory:'cavities',selectionMode:'cavity',onSelect:()=>{}});
  assert.equal(h.titles.at(-1),'Engineering Library / Cavities');
  assert.ok(button(h.nodes.content,'Back to Engineering Library'));
  assert.equal(button(h.nodes.content,'Select').disabled,false);
  await h.ui({entryCategory:'cavities'});
  assert.equal(button(h.nodes.content,'Select'),undefined);
});

test('External-port Use action requires the explicit selection mode',async()=>{
  const calls=[];
  const h=harness(async url=>{
    calls.push(url);
    if(url.startsWith('/api/catalog?'))return {total:1,items:[{id:'PORT_A',name:'Port A',family:'SAE',unit_system:'metric',thread_spec:'',usable:1,active:1}]};
    throw Error('Unexpected '+url);
  });
  await h.ui({entryCategory:'external-ports',selectionMode:'external-port',scope:'custom',onSelect:()=>{}});
  assert.ok(button(h.nodes.content,'Select'));
  assert.equal(button(h.nodes.content,'Select').disabled,false);
  assert.match(calls.at(-1),/scope=all/); // Existing selection-state default is unchanged.
  await h.ui({entryCategory:'external-ports'});
  assert.equal(button(h.nodes.content,'Select'),undefined);
  assert.match(calls.at(-1),/scope=all/);
});

test('A delayed category response cannot replace the Library dashboard',async()=>{
  let release;
  const h=harness(url=>url.startsWith('/api/catalog?')&&!url.includes('limit=1')?new Promise(resolve=>{release=resolve;}):Promise.resolve({total:0,items:[]}));
  const first=h.ui({entryCategory:'cavities'});
  await sleep(0); // The compact summary request precedes normal category loading.
  await h.ui();
  release({total:1,items:[{id:'LATE',name:'Late cavity'}]});
  await first;
  assert.equal(h.titles.at(-1),'Engineering Library');
  assert.ok(all(h.nodes.content).some(node=>node.className==='library-category-grid'));
  assert.equal(words(h.nodes.content).includes('Late cavity'),false);
});

test('Threads preserve search and page when returning from detail',async()=>{
  const calls=[];
  const h=harness(async url=>{
    calls.push(url);
    if(url.startsWith('/api/threads'))return {total:82,items:[{id:'THREAD_1',display_name:'M10x1',normalized_family:'ISO',unit_system:'metric',tap_diameter_mm:9,tapered:false,usable:true,active:true}]};
    throw Error('Unexpected '+url);
  });
  await h.ui({entryCategory:'threads'});
  const search=h.field('Search');search.value='M10';search.oninput();await sleep(200);
  assert.match(calls.at(-1),/q=M10/);
  await button(h.nodes.content,'Next').onclick();
  assert.match(calls.at(-1),/offset=40/);
  await button(h.nodes.content,'View').onclick();
  assert.match(words(h.nodes.content),/Tap drill: Ø9 mm/);
  await button(h.nodes.content,'Back to Threads').onclick();
  assert.equal(h.field('Search').value,'M10');
  assert.match(calls.at(-1),/offset=40/);
  assert.ok(button(h.nodes.content,'Back to Engineering Library'));
});

test('Cartridge identity and technical state show without audit or execution actions',async()=>{
  const item=(id,eligible)=>({relation_id:id,cavity_family:'Maker',cavity_name:'A-1',
    execution_eligible:eligible,verification_status:eligible?'CONFIRMED':'PROBABLE',
    confidence:eligible?.95:.70,resolution_status:'RESOLVED',resolution_detail:{reason:''},
    resolved_cavities:[],document_name:'Catalogue',document_revision:'R1',page_number:'7',
    evidence_text:'A-1 stated in source',source_url:'https://example.test/catalogue'});
  const h=harness(async url=>{
    if(url.startsWith('/api/cartridges?'))return {total:1,items:[{id:'cart_1',manufacturer:'Maker',model:'MODEL',function:''}]};
    if(url==='/api/engineering-library/cartridges/cart_1')return {available:false,cavity_identities:[]};
    if(url.startsWith('/api/knowledge/cartridges/'))return {total:2,items:[item('REL_SAFE',true),item('REL_REVIEW',false)]};
    throw Error('Unexpected '+url);
  });
  await h.ui({entryCategory:'cartridges'});
  await button(h.nodes.content,'View').onclick();
  assert.match(words(h.nodes.content),/Technical data not available/);
  assert.equal(words(h.nodes.content).includes('Relationship evidence'),false);
  assert.equal(button(h.nodes.content,'Place Cavity'),undefined);
  assert.equal(button(h.nodes.content,'Bind'),undefined);
  await button(h.nodes.content,'Back to Cartridges').onclick();
  assert.equal(h.titles.at(-1),'Engineering Library / Cartridges');
});
