import {test} from 'node:test';
import assert from 'node:assert/strict';
import {libraryUI} from '../web/library-ui.js';
import {libraryCategories} from '../web/library-knowledge-ui.js';

class Node{
  constructor(tag,text='',cls=''){this.tagName=tag;this.textContent=text||'';this.className=cls;this.children=[];this.value='';this.disabled=false;this.scrollTop=0;this.classList={add:()=>{}};}
  append(...children){this.children.push(...children);}
  prepend(...children){this.children.unshift(...children);}
  replaceChildren(...children){this.children=[...children];this.textContent='';}
  setAttribute(){}
  querySelectorAll(){return [];}
}
const all=n=>[n,...n.children.flatMap(all)],words=n=>all(n).map(c=>c.textContent).join(' ');
const button=(node,label)=>all(node).find(n=>n.tagName==='button'&&n.textContent===label);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const counts={cavities:[6429,63],cartridges:[15665,0],'external-ports':[446,271],threads:[833,122],materials:[12,0],tooling:[412,15],closures:[0,443],modifiers:[326,18],seals:[null,1138],fittings:[null,130],fasteners:[null,84],fluids:[null,24],'surface-treatments':[null,105],standards:[null,177],'cross-references':[null,415],inspection:[null,12],manufacturing:[null,9],documentation:[null,15],commercial:[null,9],suppliers:[null,9]};
const summaries=()=>({items:libraryCategories.map(([key,label,description,runtime])=>({key,label,description,definition_count:counts[key][0],knowledge_count:counts[key][1],browse_mode:runtime&&counts[key][0]?'definitions':'knowledge'}))});
function harness(api){
  const nodes={content:new Node('div'),dialog:new Node('div'),error:new Node('p')},fields=[],titles=[];
  const ctx={get:()=>null,$:id=>({'workflow-content':nodes.content,'workflow-dialog':nodes.dialog,'workflow-error':nodes.error}[id]),
    element:(tag,text,cls)=>new Node(tag,text,cls),api,post:async()=>{},
    field:(p,label,value,change)=>{const input=new Node('input');input.value=value;input.onchange=()=>change(input.value);p.append(input);fields.push({label,input});return input;},
    action:(p,label,fn)=>{const b=new Node('button',label);b.onclick=fn;p.append(b);return b;}};
  const ui=libraryUI(ctx,{open:title=>{titles.push(title);nodes.content.replaceChildren();},insert:()=>{}});
  return {ui,nodes,titles,field:label=>fields.filter(r=>r.label===label).at(-1)?.input};
}
function api(calls){return async url=>{
  calls.push(url);
  if(url==='/api/engineering-library/categories')return summaries();
  if(url.startsWith('/api/engineering-library/knowledge?'))return {total:85,items:[{key:'opaque-link-only',name:'Maker 123',family:'Plug',key_data:'Thread: M10',status:'Partial data'}]};
  if(url.startsWith('/api/engineering-library/knowledge/'))return {name:'Maker 123',family:'Plug',status:'Partial data',groups:[{title:'Engineering Data',fields:[{label:'Thread',value:'M10'}]}]};
  if(url.startsWith('/api/catalog?'))return {total:85,items:[{id:'PORT_A',name:'G3/8',family:'BSPP',manufacturer:'Maker',unit_system:'inch',usable:1,active:1}]};
  throw Error(url);
};}

test('one compact dashboard uses one card template and Browse action for all 20 categories',async()=>{
  const calls=[],h=harness(api(calls));await h.ui();
  const grid=all(h.nodes.content).find(n=>n.className==='library-category-grid');assert.equal(grid.children.length,20);
  for(const card of grid.children){assert.equal(card.className,'library-card library-category-card');assert.equal(all(card).filter(n=>n.tagName==='button').length,1);assert.ok(button(card,'Browse'));}
  for(const label of libraryCategories.map(row=>row[1]))assert.ok(words(grid).includes(label));
  for(const text of ['6,429 definitions · 63 knowledge','446 definitions · 271 knowledge','833 definitions · 122 knowledge','412 definitions · 15 knowledge','0 definitions · 443 knowledge'])assert.ok(words(grid).includes(text),text);
  assert.deepEqual(calls,['/api/engineering-library/categories']);
  for(const text of ['Evidence','Sources','Verification Scope','Findings','Conflicts','Variants','Raw JSON','Gate A','Gate B','Gate C','Available for browsing'])assert.equal(words(grid).includes(text),false,text);
});

test('Definitions and Knowledge retain independent searches/pages through detail and switches',async()=>{
  const calls=[],h=harness(api(calls));await h.ui({entryCategory:'external-ports'});
  h.field('Search').value='G3/8';h.field('Search').oninput();await sleep(190);
  await button(h.nodes.content,'Knowledge').onclick();assert.match(calls.at(-1),/category=external-ports/);
  h.field('Search').value='M10';h.field('Search').oninput();await sleep(190);
  await button(h.nodes.content,'Next').onclick();assert.match(calls.at(-1),/offset=40/);
  await button(h.nodes.content,'View').onclick();assert.match(words(h.nodes.content),/Thread: M10/);assert.match(words(h.nodes.content),/Partial data/);
  assert.equal(words(h.nodes.content).includes('opaque-link-only'),false);
  await button(h.nodes.content,'Back to External Ports').onclick();assert.equal(h.field('Search').value,'M10');assert.match(calls.at(-1),/offset=40/);
  await button(h.nodes.content,'Definitions').onclick();assert.equal(h.field('Search').value,'G3/8');
  await button(h.nodes.content,'Knowledge').onclick();assert.equal(h.field('Search').value,'M10');assert.match(calls.at(-1),/offset=40/);
});

test('zero-definition Closures lands on Knowledge with View only and no internal identity',async()=>{
  const calls=[],h=harness(api(calls));await h.ui({entryCategory:'closures'});assert.match(calls.at(-1),/category=closures/);
  const labels=all(h.nodes.content).filter(n=>n.tagName==='button').map(n=>n.textContent);
  for(const label of ['Place','Use','Bind','Generate','Select','+ New Custom'])assert.equal(labels.includes(label),false);
  await button(h.nodes.content,'View').onclick();assert.match(words(h.nodes.content),/Engineering Data/);
  for(const text of ['opaque-link-only','Evidence','Sources','Findings','Raw JSON'])assert.equal(words(h.nodes.content).includes(text),false);
});

test('selection workflows request runtime lists only and expose no Knowledge switch',async()=>{
  for(const [category,mode]of [['cavities','cavity'],['external-ports','external-port']]){
    const calls=[],h=harness(api(calls));await h.ui({entryCategory:category,selectionMode:mode,onSelect:()=>{}});
    assert.equal(calls.some(url=>url.includes('engineering-library')),false);
    assert.equal(button(h.nodes.content,'Knowledge'),undefined);assert.ok(button(h.nodes.content,'Select'));
  }
});

test('delayed knowledge responses cannot replace Home and failed counts stay local',async()=>{
  let release;
  const h=harness(url=>url.startsWith('/api/engineering-library/knowledge?')?new Promise(resolve=>{release=resolve;}):Promise.resolve(summaries()));
  const first=h.ui({entryCategory:'seals'});await h.ui();release({total:1,items:[{key:'OLD',name:'Late old row'}]});await first;
  assert.equal(h.titles.at(-1),'Engineering Library');assert.equal(words(h.nodes.content).includes('Late old row'),false);
  const data=summaries();data.items.find(r=>r.key==='seals').count_unavailable=true;
  const isolated=harness(async()=>data);await isolated.ui();const grid=all(isolated.nodes.content).find(n=>n.className==='library-category-grid');
  assert.ok(words(grid).includes('Count unavailable'));assert.ok(words(grid).includes('446 definitions · 271 knowledge'));
});
