import {isCavity,isPort} from './definition-role.js';
import {profileEditor} from './profile.js';
import {technicalKnowledgeUI} from './technical-knowledge-ui.js';

export function libraryUI(ctx,{open,insert,onCustomSaved=()=>{}}){
  const {$,element,field,action,api,post}=ctx,content=$('workflow-content');
  const guard=fn=>async()=>{try{await fn();$('workflow-error').textContent='';}catch(e){$('workflow-error').textContent=e.message;}};
  let generation=0;
  function placement(parent,label,callback){const button=action(parent,label,callback);if(!ctx.get()){button.disabled=true;button.title='Open or create a manifold before placing a feature.';}return button;}
  function selectOrPlace(parent,label,callback,options){return options.selectionMode==='cavity'||options.selectionMode==='external-port'?action(parent,label,callback):placement(parent,label,callback);}
  const blank=(kind='cavity')=>({id:'custom_pending',label:kind==='external-port'?'Custom external port':'Custom cavity',family:'Custom',unit_system:ctx.get()?.project_context||'metric',manufacturer:'',thread_note:'',
    stages:[{start:0,end:20,diameter:20}],zones:[{id:'port1',start:10,end:18,diameter:18,offset_u:0,offset_v:0,clip_to_cut:true}],
    clearance_diameter:24,clearance_height:20,cutting_primitives:[],boundaries:[],machining:[],usable:true,unusable_reason:'',active:true,kind});

  function validationErrors(definition){
    const errors=[];
    definition.stages.forEach((row,index)=>{
      if(!(row.end>row.start))errors.push(`Stage ${index+1}: end depth must be greater than start depth.`);
      if(index===0&&Math.abs(row.start)>1e-6)errors.push('Stage 1 must start at depth 0.');
      if(index&&Math.abs(row.start-definition.stages[index-1].end)>1e-6)errors.push(`Stage ${index+1}: start depth must equal the previous end depth.`);
      if(index&&row.diameter>definition.stages[index-1].diameter)errors.push(`Stage ${index+1}: diameter cannot increase with depth.`);
    });
    const ids=new Set();
    definition.zones.forEach((row,index)=>{
      if(ids.has(row.id))errors.push(`Interface ${index+1}: duplicate interface ID.`);ids.add(row.id);
      if(!(row.end>row.start))errors.push(`Interface ${index+1}: end depth must be greater than start depth.`);
      if(!definition.cutting_primitives.length&&!definition.stages.some(stage=>stage.start<=row.start&&row.end<=stage.end&&row.diameter<=stage.diameter))errors.push(`Interface ${index+1}: hydraulic window must lie inside a machining stage.`);
    });
    definition.cutting_primitives.forEach((row,index)=>{if(!(row.end>row.start))errors.push(`Cutting primitive ${index+1}: end depth must be greater than start depth.`);if(row.kind==='annulus'&&!(row.inner_diameter<row.diameter))errors.push(`Cutting primitive ${index+1}: inner diameter must be smaller than outer diameter.`);});
    const outer=Math.max(0,...definition.stages.map(row=>row.diameter),...definition.cutting_primitives.map(row=>2*Math.hypot(row.offset_u||0,row.offset_v||0)+Math.max(row.diameter||0,row.end_diameter||0)));
    if(definition.clearance_diameter<outer)errors.push(`Clearance diameter must cover the ${outer.toFixed(2)} mm outer profile.`);
    definition.boundaries.forEach((row,index)=>{if(row.circle&&!(row.circle[2]>0))errors.push(`Boundary ${index+1}: circle radius must be positive.`);if(!row.circle&&(row.points||[]).length<3)errors.push(`Boundary ${index+1}: polygon requires at least three points.`);});
    if(definition.kind==='external-port'&&(definition.zones.length!==1||definition.zones[0]?.offset_u||definition.zones[0]?.offset_v))errors.push('External port requires exactly one centered hydraulic interface.');
    return errors;
  }

  function editCustom(source=null,backOptions={},requestedKind=null){
    ++generation;const kind=requestedKind||source?.kind||'cavity',noun=kind==='external-port'?'External Port':'Cavity',definition=structuredClone(source||blank(kind));definition.id='custom_pending';definition.kind=kind;definition.active=true;definition.usable=true;definition.unusable_reason='';
    const render=()=>{
      open(source?`Duplicate as Custom ${noun}`:`Create Custom ${noun}`);content.append(element('p',`Saving creates a new stable SQLite ${noun.toLowerCase()} ID. The source/master definition and existing projects are not changed.`));
      const edit=(parent,label,value,set,options=null,numeric=false)=>field(parent,label,value,v=>{set(v);render();},options,numeric);
      const basics=element('section',null,'editor-grid');content.append(basics);
      edit(basics,'Display name',definition.label,v=>definition.label=v);edit(basics,'Engineering units',definition.unit_system,v=>definition.unit_system=v,{metric:'Metric',inch:'Inch',custom:'Custom'});edit(basics,'Family / type',definition.family,v=>definition.family=v);edit(basics,'Manufacturer',definition.manufacturer,v=>definition.manufacturer=v);edit(basics,'Thread / note',definition.thread_note,v=>definition.thread_note=v);edit(basics,'Clearance diameter / mm',definition.clearance_diameter,v=>definition.clearance_diameter=v,null,true);edit(basics,'Clearance height / mm',definition.clearance_height,v=>definition.clearance_height=v,null,true);for(const message of validationErrors(definition).filter(value=>value.startsWith('Clearance diameter')))basics.append(element('p',message,'error'));

      const rowActions=(parent,rows,index,make)=>{const bar=element('div',null,'action-row');parent.append(bar);action(bar,'Duplicate',()=>{rows.splice(index+1,0,structuredClone(rows[index]));render();});action(bar,'Move up',()=>{if(index){[rows[index-1],rows[index]]=[rows[index],rows[index-1]];render();}});action(bar,'Move down',()=>{if(index<rows.length-1){[rows[index+1],rows[index]]=[rows[index],rows[index+1]];render();}});action(bar,'Delete',()=>{rows.splice(index,1);if(!rows.length&&make&&rows===definition.stages)rows.push(make());render();});};
      const section=(title,rows,make,build)=>{const singular={ 'Machining stages':'Machining stage','Cutting primitives':'Cutting primitive','Hydraulic interfaces':'Hydraulic interface','Supported boundaries':'Supported boundary','Machining operations':'Machining operation'}[title]||title;const box=element('section',null,'library-card');box.append(element('h3',`${title} · ${rows.length}`));content.append(box);rows.forEach((item,index)=>{const row=element('section',null,'port-row');row.append(element('h4',`${singular} ${index+1}`));box.append(row);build(row,item,index);rowActions(row,rows,index,make);});action(box,`+ Add ${singular.toLowerCase()}`,()=>{rows.push(make());render();});};

      section('Machining stages',definition.stages,()=>{const previous=definition.stages.at(-1);return {start:previous?.end||0,end:(previous?.end||0)+10,diameter:previous?.diameter||10};},(row,item,index)=>{const type=field(row,'Type','Cylinder',()=>{},{cylinder:'Cylinder'});type.disabled=true;edit(row,'Start depth / mm',item.start,v=>item.start=v,null,true);edit(row,'End depth / mm',item.end,v=>item.end=v,null,true);edit(row,'Diameter / mm',item.diameter,v=>item.diameter=v,null,true);for(const message of validationErrors(definition).filter(value=>value.startsWith(`Stage ${index+1}:`)))row.append(element('p',message,'error'));});
      section('Cutting primitives',definition.cutting_primitives,()=>({kind:'cylinder',start:0,end:10,diameter:10,end_diameter:10,inner_diameter:0,offset_u:0,offset_v:0,source_ref:'Custom'}),(row,item,index)=>{edit(row,'Type',item.kind,v=>item.kind=v,{cylinder:'Cylinder',cone:'Cone',annulus:'Annulus'});edit(row,'Start depth / mm',item.start,v=>item.start=v,null,true);edit(row,'End depth / mm',item.end,v=>item.end=v,null,true);edit(row,'Diameter / mm',item.diameter,v=>item.diameter=v,null,true);if(item.kind==='cone')edit(row,'End diameter / mm',item.end_diameter,v=>item.end_diameter=v,null,true);if(item.kind==='annulus')edit(row,'Inner diameter / mm',item.inner_diameter,v=>item.inner_diameter=v,null,true);edit(row,'Offset U / mm',item.offset_u||0,v=>item.offset_u=v,null,true);edit(row,'Offset V / mm',item.offset_v||0,v=>item.offset_v=v,null,true);for(const message of validationErrors(definition).filter(value=>value.startsWith(`Cutting primitive ${index+1}:`)))row.append(element('p',message,'error'));});
      section('Hydraulic interfaces',definition.zones,()=>({id:`port${definition.zones.length+1}`,start:0,end:5,diameter:5,offset_u:0,offset_v:0,clip_to_cut:true}),(row,item,index)=>{edit(row,'Interface ID',item.id,v=>item.id=v);edit(row,'Start depth / mm',item.start,v=>item.start=v,null,true);edit(row,'End depth / mm',item.end,v=>item.end=v,null,true);edit(row,'Hydraulic diameter / mm',item.diameter,v=>item.diameter=v,null,true);edit(row,'Offset U / mm',item.offset_u||0,v=>item.offset_u=v,null,true);edit(row,'Offset V / mm',item.offset_v||0,v=>item.offset_v=v,null,true);edit(row,'Clip to machining volume',String(!!item.clip_to_cut),v=>item.clip_to_cut=v==='true',{true:'Yes',false:'No'});for(const message of validationErrors(definition).filter(value=>value.startsWith(`Interface ${index+1}:`)))row.append(element('p',message,'error'));});
      section('Supported boundaries',definition.boundaries,()=>({category:'mounting-footprint',circle:[0,0,10],points:[],height:0}),(row,item,index)=>{const type=item.circle?'circle':'polygon';edit(row,'Boundary type',type,v=>{if(v==='circle'){item.circle=[0,0,10];item.points=[];}else{item.circle=null;item.points=[[0,0],[10,0],[0,10]];}},{circle:'Circle',polygon:'Polygon'});edit(row,'Category',item.category,v=>item.category=v,{'mounting-footprint':'Mounting footprint','external-body':'External body',service:'Service',tool:'Tool'});edit(row,'Height / mm',item.height||0,v=>item.height=v,null,true);if(item.circle){for(const [i,label]of ['Center U / mm','Center V / mm','Radius / mm'].entries())edit(row,label,item.circle[i],v=>item.circle[i]=v,null,true);}else{for(const [i,point]of (item.points||[]).entries()){const pointRow=element('div',null,'field-row');row.append(pointRow);edit(pointRow,`Point ${i+1} U`,point[0],v=>point[0]=v,null,true);edit(pointRow,`Point ${i+1} V`,point[1],v=>point[1]=v,null,true);action(pointRow,'Delete point',()=>{item.points.splice(i,1);render();});}action(row,'+ Add polygon point',()=>{item.points.push([0,0]);render();});}for(const message of validationErrors(definition).filter(value=>value.startsWith(`Boundary ${index+1}:`)))row.append(element('p',message,'error'));});
      section('Machining operations',definition.machining,()=>({operation:'',tool:'',depth:null,note:'',source:''}),(row,item)=>{edit(row,'Operation',item.operation||'',v=>item.operation=v);edit(row,'Tool / cutter',item.tool||'',v=>item.tool=v);edit(row,'Depth / mm',item.depth??'',v=>item.depth=v===''?null:v,null,true);edit(row,'Note',item.note||'',v=>item.note=v);edit(row,'Source',item.source||'',v=>item.source=v);});

      const errors=validationErrors(definition);if(errors.length){const box=element('section',null,'error');box.append(element('strong','Correct these fields before saving:'));for(const value of errors)box.append(element('p',value));content.append(box);}profileEditor(ctx,content,definition,{editable:false});
      const advanced=element('details');advanced.append(element('summary','Advanced · Raw engineering JSON (import/debug only)'));content.append(advanced);for(const [label,key]of [['Machining stages','stages'],['Cutting primitives','cutting_primitives'],['Hydraulic interfaces','zones'],['Supported boundaries','boundaries'],['Machining operations','machining']]){const wrap=element('label',label+' JSON','field'),input=element('textarea');input.value=JSON.stringify(definition[key],null,2);input.spellcheck=false;input.onchange=()=>{try{const value=JSON.parse(input.value);if(!Array.isArray(value))throw Error('Expected a JSON array');definition[key]=value;render();}catch(error){$('workflow-error').textContent=`${label}: ${error.message}`;}};wrap.append(input);advanced.append(wrap);}
      const buttons=element('div',null,'action-row');content.append(buttons);const returnToCategory=()=>backToCategory(kind==='external-port'?'external-ports':'cavities',backOptions);const save=action(buttons,`Save New Custom ${noun}`,guard(async()=>{const invalid=validationErrors(definition);if(invalid.length)throw Error(invalid[0]);const saved=await post(kind==='external-port'?'/api/catalog/custom-external-port':'/api/catalog/custom-cavity',{definition});if(kind==='cavity')onCustomSaved(saved);open(`Custom ${noun.toLowerCase()} saved`);content.append(element('h3',saved.label),element('p',`${saved.id}\n${saved.unit_system.toUpperCase()} · ${saved.family||'Custom'}\nThe new record is active in the SQLite Engineering Library.`));if(kind==='cavity')placement(content,'Place this cavity',()=>insert(saved));else if(backOptions.selectionMode==='external-port'&&backOptions.onSelect)action(content,'Use this external port',()=>backOptions.onSelect(saved));action(content,`Back to ${kind==='external-port'?'External Ports':'Cavities'}`,returnToCategory);}));save.classList.add('primary');save.disabled=!!errors.length;action(buttons,'Cancel',returnToCategory);
    };render();
  }

  const labels={cavities:'Cavities',cartridges:'Cartridges','external-ports':'External Ports',threads:'Threads',materials:'Materials & Stock',tooling:'Tooling',closures:'Closures & Plugs',modifiers:'Machining Modifiers'};
  const state={
    cavities:{q:'',unit:'',kind:'cavity',family:'',manufacturer:'',thread:'',status:'all',scope:'all',include_deleted:false,offset:0,limit:30},
    cartridges:{q:'',offset:0},
    'external-ports':{q:'',unit:'',standard:'',kind:'port_definition',scope:'all',status:'all',include_deleted:false,offset:0,limit:50},
    threads:{q:'',unit:'',family:'',usable_only:false,offset:0,limit:40},
    materials:{q:'',offset:0},tooling:{q:'',type:'',unit:'',diameter:'',offset:0},
    closures:{q:'',offset:0},modifiers:{q:'',kind:'',unit:'',offset:0},
  };
  const selectionState={cavities:{...state.cavities},'external-ports':{...state['external-ports']}};
  const scroll={};
  function rememberScroll(category){scroll[category]=$('workflow-dialog')?.scrollTop||0;}
  function restoreScroll(category){const dialog=$('workflow-dialog');if(dialog)dialog.scrollTop=scroll[category]||0;}
  function backToCategory(category,options={}){const next={...options,entryCategory:category};delete next.recordId;return library(next);}
  function selectionCallback(port,options){
    if(port)return options.selectionMode==='external-port'?options.onSelect:null;
    if(options.selectionMode==='cavity')return options.onSelect||null;
    return !options.selectionMode||options.selectionMode==='browse'?insert:null;
  }
  const displayMm=value=>value==null?'—':Number(Number(value).toFixed(4));
  function categoryHeader(category){action(content,'Back to Engineering Library',()=>home());content.append(element('p',`${labels[category]} · SQLite engineering records`));}

  function home(){
    const token=++generation;open('Engineering Library');content.append(element('p','Browse source-backed engineering definitions by category. Compatibility evidence stays with its Cartridge and Cavity.'));
    const grid=element('div',null,'library-category-grid');content.append(grid);
    const categories=[
      ['cavities','Machining geometry and hydraulic interfaces',async()=>(await api('/api/catalog?kind=cavity&limit=1')).total,'definitions'],
      ['cartridges','Valve identities, compatibility and source evidence',async()=>(await api('/api/cartridges?limit=1')).total,'cartridges'],
      ['external-ports','Reusable hydraulic port machining definitions',async()=>(await api('/api/catalog?kind=port_definition&limit=1')).total,'definitions'],
      ['threads','Reusable thread and tap definitions',async()=>(await api('/api/threads?usable_only=false&limit=1')).total,'definitions'],
      ['materials','Engineering stock and sourced material knowledge',async()=>{const rows=await Promise.all([api('/api/materials'),api('/api/materials/technical')]);return rows[0].items.length+rows[1].items.filter(r=>r.research_only).length;},'materials'],
      ['tooling','Drill, flat-bottom-drill and spotface tools',async()=>{const rows=await Promise.all(['drill','flat-bottom-drill','spotface'].map(type=>api('/api/tools?'+new URLSearchParams({type,usable_only:false}))));return rows.reduce((sum,row)=>sum+(row.total??row.items.length),0);},'tools'],
      ['closures','Construction closures and plugs',async()=>(await api('/api/closures')).total,'definitions'],
      ['modifiers','O-ring grooves, counterbores and undercuts',async()=>(await api('/api/machining-modifiers?usable_only=false')).total,'definitions'],
    ];
    for(const [key,description,count,noun] of categories){
      const card=element('section',null,'library-card library-category-card'),quantity=element('p','Loading record count…','library-category-count'),availability=element('p','Checking availability…','property-note');
      card.append(element('h3',labels[key]),element('p',description),quantity,availability);grid.append(card);
      action(card,'Open →',()=>backToCategory(key));
      Promise.resolve().then(count).then(total=>{if(token!==generation)return;quantity.textContent=`${Number(total).toLocaleString()} ${noun}`;availability.textContent=total?'Available for browsing':'No records collected yet';})
        .catch(()=>{if(token!==generation)return;quantity.textContent='Count unavailable';availability.textContent='Open this category to retry';});
    }
  }

  function sourceLink(parent,value){try{const url=new URL(value);if(!['http:','https:'].includes(url.protocol)||!url.hostname)return;const link=element('a','Open Source');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';parent.append(link);}catch{}}

  function evidenceCard(parent,item,options){const card=element('section',null,'library-card');parent.append(card);card.append(element('h4',`${item.cavity_family} · ${item.cavity_name}`),element('p',`${item.execution_eligible?'EXECUTION SAFE':'EVIDENCE ONLY'} · ${item.verification_status} · ${Number(item.confidence).toFixed(2)} · ${item.resolution_status}`));if(item.resolution_detail?.reason)card.append(element('p','Resolution: '+item.resolution_detail.reason,'property-note'));for(const cavity of item.resolved_cavities||[]){const line=element('div',null,'compatible-cavity');line.append(element('strong',`${cavity.name} · ${cavity.unit_system.toUpperCase()}`),element('p',cavity.usable?'Geometry usable':'Geometry unavailable: '+cavity.unusable_reason));action(line,'View cavity',guard(async()=>{const result=await api('/api/catalog/record?'+new URLSearchParams({id:cavity.cavity_id}));viewDefinition(result.definition,{...options,readOnly:true});}));card.append(line);}if(!item.resolved_cavities?.length)card.append(element('p','No executable cavity identity resolved.','property-note'));for(const [label,value] of [['Document',item.document_name],['Revision',item.document_revision],['Page',item.page_number],['Evidence',item.evidence_text],['Source',item.source_url]])card.append(element('p',`${label}: ${value||'Not collected'}`));sourceLink(card,item.source_url);return card;}

  function viewDefinition(definition,options={}){
    const category=options.entryCategory|| (definition.kind==='external-port'?'external-ports':'cavities');
    const token=++generation,port=definition.kind==='external-port',custom=definition.id.startsWith('custom_')||definition.id.startsWith('legacy_');
    open((port?'External Port':'Cavity')+' Definition · '+definition.label);
    content.append(element('p',`${custom?'CUSTOM / LOCAL':'PMC MASTER'} · ${definition.active?'ACTIVE':'ARCHIVED'} · ${definition.unit_system.toUpperCase()} · ${definition.family||'Family unspecified'}\nEngineering reference: ${definition.id}`));
    profileEditor(ctx,content,definition,{editable:false,interfaceNames:options.interfaceNames||{}});
    const row=element('div',null,'action-row');content.append(row);
    const select=selectionCallback(port,options);
    if(definition.active&&definition.usable&&!options.readOnly&&select)selectOrPlace(row,options.actionLabel||(port?'Use External Port':'Place Cavity'),()=>select(definition),options);
    if(!options.readOnly)action(row,'Duplicate as Custom',()=>editCustom(definition,options));
    if(custom&&!options.readOnly)action(row,definition.active?'Archive':'Restore',guard(async()=>{const saved=await post('/api/library/visibility',{id:definition.id,deleted:definition.active});viewDefinition(saved,options);}));
    action(row,'Back to '+labels[category],()=>backToCategory(category,options));
    if(!port){
      const reverse=element('section',null,'library-list'),safeList=element('section',null,'library-list'),otherList=element('section',null,'library-list'),pager=element('div',null,'action-row');content.append(element('h3','Compatible Cartridges'),reverse);reverse.append(element('h4','Execution-safe'),safeList,element('h4','Evidence only'),otherList,pager);
      let offset=0;const load=async()=>{const evidence=await api('/api/knowledge/cavities/'+encodeURIComponent(definition.id)+'/cartridges?'+new URLSearchParams({offset,limit:100}));if(token!==generation)return;for(const item of evidence.items){const target=item.execution_eligible?safeList:otherList;const card=evidenceCard(target,item,{...options,readOnly:true});card.prepend(element('p',`${item.manufacturer} ${item.cartridge_part_number}`));}pager.replaceChildren(element('span',`Showing ${Math.min(offset+evidence.items.length,evidence.total)} / ${evidence.total} evidence records`));if(offset+evidence.items.length<evidence.total)action(pager,'More evidence',guard(async()=>{offset+=evidence.items.length;await load();}));if(!evidence.total){safeList.append(element('p','None'));otherList.append(element('p','None'));}};
      load().catch(error=>{if(token===generation)reverse.replaceChildren(element('p','Cartridge reverse lookup failed: '+error.message,'error'));});
    }
  }

  async function cavities(options={}){
    const category='cavities',query=options.selectionMode?selectionState.cavities:state.cavities,token=++generation,select=selectionCallback(false,options);open(options.title||labels[category]);categoryHeader(category);
    const create=element('div',null,'action-row');content.append(create);action(create,'Create Custom Cavity',()=>editCustom(null,{...options,entryCategory:category}));
    if(!ctx.get())content.append(element('p','Browse definitions here. Open or create a manifold to place a feature.','property-note'));
    const filters=element('div',null,'editor-grid'),list=element('div',null,'library-list'),pager=element('div',null,'action-row');content.append(filters,list,pager);
    let request=0,timer;
    const load=async()=>{const current=++request;list.replaceChildren(element('p','Loading cavity definitions…','loading-state'));pager.replaceChildren();try{const result=await api('/api/catalog?'+new URLSearchParams(query));if(token!==generation||current!==request)return;list.replaceChildren(element('p',`${result.total.toLocaleString()} matching cavities`));for(const row of result.items){const card=element('section',null,'library-card'),custom=row.id.startsWith('custom_')||row.id.startsWith('legacy_');list.append(card);card.append(element('h3',row.name),element('p',`${custom?'CUSTOM / LOCAL':'PMC MASTER'} · ${row.active?'ACTIVE':'ARCHIVED'} · ${row.manufacturer||'Manufacturer unspecified'} · ${row.family||'Family unspecified'} · ${row.unit_system.toUpperCase()}\n${row.thread_spec||'No thread specification'}\nEngineering reference: ${row.id}`));if(!row.usable)card.append(element('p','Unavailable: '+row.unusable_reason,'error'));action(card,'View Definition',guard(async()=>{rememberScroll(category);const payload=await api('/api/catalog/record?'+new URLSearchParams({id:row.id}));if(!isCavity(payload.definition))throw Error('Selected record is not a cavity.');viewDefinition(payload.definition,{...options,entryCategory:category});}));if(row.usable&&row.active&&select)selectOrPlace(card,options.actionLabel||'Place Cavity',guard(async()=>{const definition=await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(!isCavity(definition))throw Error('Selected record is not a cavity.');select(definition);}),options);if(custom)action(card,row.active?'Archive':'Restore',guard(async()=>{await post('/api/library/visibility',{id:row.id,deleted:!!row.active});load();}));}if(query.offset)action(pager,'Previous page',()=>{query.offset=Math.max(0,query.offset-query.limit);scroll[category]=0;load();});pager.append(element('span',result.total?`${query.offset+1}–${Math.min(query.offset+query.limit,result.total)} / ${result.total}`:'0 results'));if(query.offset+query.limit<result.total)action(pager,'Next page',()=>{query.offset+=query.limit;scroll[category]=0;load();});restoreScroll(category);}catch(e){if(token!==generation||current!==request)return;list.replaceChildren(element('p','Cavity catalog failed to load: '+e.message,'error'));}};
    const update=(key,value)=>{query[key]=value;query.offset=0;scroll[category]=0;clearTimeout(timer);timer=setTimeout(load,180);};
    for(const [label,key,choices] of [['Engineering units','unit',{'':'All units',metric:'Metric',inch:'Inch',custom:'Custom'}],['Family / type','family',null],['Manufacturer','manufacturer',null],['Thread','thread',null],['Library scope','scope',{all:'Master and custom',master:'PMC master',custom:'Custom / local'}],['Engineering availability','status',{all:'Usable and unavailable',usable:'Usable only',unavailable:'Unavailable only'}],['Show archived custom/local','include_deleted',{false:'No',true:'Yes'}]])field(filters,label,query[key],value=>update(key,value),choices);
    const search=field(filters,'Search cavity',query.q,value=>update('q',value));search.oninput=()=>update('q',search.value);await load();
  }

  async function externalPorts(options={}){
    const category='external-ports',query=options.selectionMode?selectionState[category]:state[category],token=++generation,select=selectionCallback(true,options);open(labels[category]);categoryHeader(category);
    if(options.scope)query.scope=options.scope;
    content.append(element('p','Reusable external-port machining definitions. One-off Custom Straight Bore remains project-only.'));
    action(content,'Create Custom External Port',()=>editCustom(null,{...options,entryCategory:category},'external-port'));
    const filters=element('div',null,'editor-grid'),list=element('div',null,'library-list'),pager=element('div',null,'action-row');content.append(filters,list,pager);let timer,request=0;
    const load=async()=>{const current=++request;list.replaceChildren(element('p','Loading external ports…','loading-state'));try{const result=await api('/api/catalog?'+new URLSearchParams(query));if(token!==generation||current!==request)return;list.replaceChildren(element('p',`${result.total.toLocaleString()} matching external ports`));for(const row of result.items){const custom=row.id.startsWith('custom_')||row.id.startsWith('legacy_'),card=element('section',null,'library-card');card.append(element('h3',row.name),element('p',`${custom?'CUSTOM / LOCAL':'PMC MASTER'} · ${row.active?'ACTIVE':'ARCHIVED'} · ${row.family||'Family unspecified'} · ${row.unit_system.toUpperCase()}\n${row.thread_spec||'No thread specification'}`));if(!row.usable)card.append(element('p','Unavailable: '+row.unusable_reason,'error'));list.append(card);action(card,'View Definition',guard(async()=>{rememberScroll(category);const payload=await api('/api/catalog/record?'+new URLSearchParams({id:row.id}));viewDefinition(payload.definition,{...options,entryCategory:category});}));if(row.active&&row.usable&&select)action(card,options.actionLabel||'Use External Port',guard(async()=>select(await api('/api/catalog/definition?'+new URLSearchParams({id:row.id})))));if(custom)action(card,row.active?'Archive':'Restore',guard(async()=>{await post('/api/library/visibility',{id:row.id,deleted:!!row.active});load();}));}pager.replaceChildren();if(query.offset)action(pager,'Previous page',()=>{query.offset=Math.max(0,query.offset-query.limit);scroll[category]=0;load();});pager.append(element('span',result.total?`${query.offset+1}–${Math.min(query.offset+query.limit,result.total)} / ${result.total}`:'0 results'));if(query.offset+query.limit<result.total)action(pager,'Next page',()=>{query.offset+=query.limit;scroll[category]=0;load();});restoreScroll(category);}catch(e){if(token===generation&&current===request)list.replaceChildren(element('p','External ports failed to load: '+e.message,'error'));}};
    const update=(key,value)=>{query[key]=value;query.offset=0;scroll[category]=0;clearTimeout(timer);timer=setTimeout(load,150);};
    field(filters,'Port standard',query.standard,value=>update('standard',value),{'':'All source-backed standards',...Object.fromEntries(['BSPP','BSPT','NPT','NPTF','SAE_ORB','ISO_6149','SAE_J518','OTHER'].map(value=>[value,value.replaceAll('_',' ')]))});
    field(filters,'Native definition',query.unit,value=>update('unit',value),{'':'All',metric:'Metric-native',inch:'Inch-native',custom:'Custom'});
    field(filters,'Library scope',query.scope,value=>update('scope',value),{all:'Master and custom',master:'PMC master',custom:'Custom / local'});
    field(filters,'Engineering availability',query.status,value=>update('status',value),{all:'Usable and unavailable',usable:'Usable only',unavailable:'Unavailable only'});
    field(filters,'Show archived custom/local',query.include_deleted,value=>update('include_deleted',value),{false:'No',true:'Yes'});
    const search=field(filters,'Search external ports',query.q,value=>update('q',value));search.oninput=()=>update('q',search.value);await load();
  }

  async function cartridgeDetail(cartridge,options){
    const category='cartridges',token=++generation;rememberScroll(category);open('Cartridge · '+cartridge.manufacturer+' '+cartridge.model);
    action(content,'Back to Cartridges',()=>backToCategory(category,options));content.append(element('p',cartridge.primary_function||cartridge.function||'Read-only technical knowledge and relationship evidence.'));
    const technical=element('section');technical.append(element('p','Loading technical knowledge…','loading-state'));content.append(technical);
    const technicalLoad=(async()=>{try{const data=await api('/api/cartridges/'+encodeURIComponent(cartridge.id)+'/technical');if(token!==generation)return;technical.replaceChildren();technicalKnowledgeUI(ctx,technical,data,'/api/cartridges/'+encodeURIComponent(cartridge.id)+'/technical',()=>token===generation);}catch(error){if(token===generation)technical.replaceChildren(element('p','Technical knowledge unavailable: '+error.message,'error'));}})();
    const safe=element('section',null,'library-list'),other=element('section',null,'library-list'),pager=element('div',null,'action-row');content.append(element('h3','Confirmed / Execution-safe cavities'),safe,element('h3','Other evidence'),other,pager);
    let offset=0;const load=async()=>{const result=await api('/api/knowledge/cartridges/'+encodeURIComponent(cartridge.id)+'/cavities?'+new URLSearchParams({offset,limit:100}));if(token!==generation)return;for(const item of result.items)evidenceCard(item.execution_eligible?safe:other,item,{...options,entryCategory:category,readOnly:true});pager.replaceChildren(element('span',`Showing ${Math.min(offset+result.items.length,result.total)} / ${result.total} evidence records`));if(offset+result.items.length<result.total)action(pager,'More evidence',guard(async()=>{offset+=result.items.length;await load();}));};await load();await technicalLoad;
  }

  async function cartridges(options={}){
    const category='cartridges',query=state[category],token=++generation;open(labels[category]);categoryHeader(category);
    content.append(element('p','Search Cartridge identities and review execution compatibility and source evidence.'));
    const filters=element('div',null,'editor-grid'),list=element('div',null,'library-list'),pager=element('div',null,'action-row');content.append(filters,list,pager);let timer,request=0;
    const load=async()=>{const current=++request;try{const result=await api('/api/cartridges?'+new URLSearchParams({q:query.q,offset:query.offset,limit:50}));if(current!==request||token!==generation)return;list.replaceChildren(element('p',`${result.total} matching cartridges`));for(const cartridge of result.items){const card=element('section',null,'library-card');card.append(element('h3',`${cartridge.manufacturer} ${cartridge.model}`),element('p',cartridge.primary_function||cartridge.function||'Function not collected'),element('p',`Base: ${cartridge.base_model||'Not established'} · ${cartridge.disposition||'Not researched'} · ${cartridge.technical_evidence_count||0} technical evidence records`));list.append(card);action(card,'View Cartridge',guard(()=>{rememberScroll(category);return cartridgeDetail(cartridge,options);}));}pager.replaceChildren(element('span',result.total?`${query.offset+1}–${Math.min(query.offset+50,result.total)} / ${result.total}`:'0 results'));if(query.offset)action(pager,'Previous page',()=>{query.offset-=50;scroll[category]=0;load();});if(query.offset+50<result.total)action(pager,'Next page',()=>{query.offset+=50;scroll[category]=0;load();});restoreScroll(category);}catch(error){if(current===request&&token===generation)list.replaceChildren(element('p','Cartridge search failed: '+error.message,'error'));}};
    const search=field(filters,'Search cartridge model or manufacturer',query.q,value=>{query.q=value;query.offset=0;scroll[category]=0;});search.oninput=()=>{query.q=search.value;query.offset=0;scroll[category]=0;clearTimeout(timer);timer=setTimeout(load,150);};await load();
  }

  async function readonlyDetail(category,row,options={}){
    rememberScroll(category);const token=++generation;open(labels[category]+' · '+(category==='tooling'?`${row.tool_type} · Ø${displayMm(row.diameter_mm)} mm`:(row.display_name||row.name||row.model||row.id)));
    action(content,'Back to '+labels[category],()=>backToCategory(category,options));
    if(category==='materials'&&(row.research_only||row.technical_identity_id)){const host=element('section');content.append(host);try{const base='/api/materials/technical/'+encodeURIComponent(row.technical_identity_id||row.id),data=await api(base);if(token!==generation)return;technicalKnowledgeUI(ctx,host,data,base,()=>token===generation,{material:true});}catch(error){if(token===generation)host.append(element('p','Material knowledge unavailable: '+error.message,'error'));}return;}
    const card=element('section',null,'library-card');content.append(card);
    const line=(label,value)=>card.append(element('p',`${label}: ${value===null||value===undefined||value===''?'Not collected':value}`));
    line('Engineering ID',row.id);line('Active',row.active?'Yes':'No');
    if(category==='threads'){for(const [name,value] of [['Family',row.normalized_family||row.family],['Designation',row.display_name],['Nominal size',row.nominal_size],['Native unit',row.unit_system],['Tap diameter',row.tap_diameter_mm==null?'Not collected':`${displayMm(row.tap_diameter_mm)} mm`],['Pitch / TPI',row.pitch_tpi],['Class',row.thread_class],['Applicability',row.applicability],['Form',row.tapered?'Tapered':'Parallel'],['Usable',row.usable?'Yes':'No'],['Reason',row.unusable_reason]])line(name,value);}
    if(category==='materials'){line('Material',row.display_name);line('Type',row.material_type);card.append(element('h3','Available stock sizes'));for(const stock of row.stock||[]){const item=element('section',null,'library-card');item.append(element('strong',`${stock.unit_system.toUpperCase()} · ${stock.size_1_mm} × ${stock.size_2_mm} mm`),element('p',`Machining allowance: ${stock.allowance_1_mm} × ${stock.allowance_2_mm} mm · ${stock.active?'ACTIVE':'ARCHIVED'}`));card.append(item);}if(!row.stock?.length)line('Stock','No source-backed stock sizes');}
    if(category==='tooling'){for(const [name,value] of [['Type',row.tool_type],['Native unit',row.unit_system],['Diameter',`${displayMm(row.diameter_mm)} mm`],['Maximum depth',`${displayMm(row.max_depth_mm)} mm`],['Usable',row.usable?'Yes':'No']])line(name,value);}
    if(category==='closures'){for(const [name,value] of [['Display name',row.display_name],['Model',row.model],['Construction port ID',row.construction_port_definition_id],['Construction port',row.construction_port_name],['Engagement',row.engagement_mm==null?'Not collected':`${row.engagement_mm} mm`],['Usable',row.usable?'Yes':'No'],['Reason',row.unusable_reason]])line(name,value);line('Envelope',JSON.stringify(row.envelope));line('Machining',JSON.stringify(row.machining));}
    if(category==='modifiers'){for(const [name,value] of [['Display name',row.display_name],['Kind',row.kind],['Native unit',row.unit_system],['Usable',row.usable?'Yes':'No'],['Reason',row.unusable_reason]])line(name,value);line('Primitives',JSON.stringify(row.primitives));line('Machining',JSON.stringify(row.machining));}
  }

  async function threads(options={}){
    const category='threads',query=state[category],token=++generation;open(labels[category]);categoryHeader(category);
    const filters=element('div',null,'editor-grid'),list=element('div',null,'library-list'),pager=element('div',null,'action-row');content.append(filters,list,pager);let request=0,timer;
    const load=async()=>{const current=++request;list.replaceChildren(element('p','Loading thread definitions…','loading-state'));try{const result=await api('/api/threads?'+new URLSearchParams(query));if(token!==generation||current!==request)return;list.replaceChildren(element('p',`${result.total} matching threads`));for(const row of result.items){const card=element('section',null,'library-card');card.append(element('h3',row.display_name),element('p',`${row.normalized_family} · ${row.unit_system.toUpperCase()} · tap Ø${displayMm(row.tap_diameter_mm)} mm · ${row.tapered?'Tapered':'Parallel'} · ${row.usable?'Usable':'Unavailable: '+row.unusable_reason}`));list.append(card);action(card,'View Thread',()=>readonlyDetail(category,row,options));}if(!result.items.length)list.append(element('p','No thread definitions match these filters.'));pager.replaceChildren(element('span',result.total?`${query.offset+1}–${Math.min(query.offset+query.limit,result.total)} / ${result.total}`:'0 results'));if(query.offset)action(pager,'Previous page',()=>{query.offset=Math.max(0,query.offset-query.limit);scroll[category]=0;load();});if(query.offset+query.limit<result.total)action(pager,'Next page',()=>{query.offset+=query.limit;scroll[category]=0;load();});restoreScroll(category);}catch(e){if(token===generation&&current===request)list.replaceChildren(element('p','Threads failed to load: '+e.message,'error'));}};
    const update=(key,value)=>{query[key]=value;query.offset=0;scroll[category]=0;clearTimeout(timer);timer=setTimeout(load,160);};
    field(filters,'Thread family',query.family,value=>update('family',value));field(filters,'Native unit',query.unit,value=>update('unit',value),{'':'All',metric:'Metric',inch:'Inch'});field(filters,'Usability',query.usable_only,value=>update('usable_only',value),{false:'All definitions',true:'Usable only'});
    const search=field(filters,'Search thread designation',query.q,value=>update('q',value));search.oninput=()=>update('q',search.value);await load();
  }

  async function readonlyCategory(category,options={}){
    const query=state[category],token=++generation;open(labels[category]);categoryHeader(category);
    const filters=element('div',null,'editor-grid'),list=element('div',null,'library-list'),pager=element('div',null,'action-row');content.append(filters,list,pager);
    let request=0,timer;
    const fetchRows=async()=>{
      if(category==='materials'){const results=await Promise.all([api('/api/materials'),api('/api/materials/technical')]);return [...results[0].items,...results[1].items.filter(row=>row.research_only)];}
      if(category==='tooling'){const results=await Promise.all(['drill','flat-bottom-drill','spotface'].map(type=>api('/api/tools?'+new URLSearchParams({type,usable_only:false}))));return results.flatMap(result=>result.items);}
      if(category==='closures')return (await api('/api/closures')).items;
      return (await api('/api/machining-modifiers?usable_only=false')).items;
    };
    const load=async()=>{const current=++request;list.replaceChildren(element('p','Loading '+labels[category]+'…','loading-state'));try{const all=await fetchRows();if(token!==generation||current!==request)return;const phrase=query.q.toLowerCase().trim(),matches=all.filter(row=>{
        const name=[row.display_name,row.name,row.model,row.material_type,row.tool_type,row.kind,row.id].join(' ').toLowerCase();
        if(phrase&&!name.includes(phrase))return false;
        if(query.unit&&row.unit_system!==query.unit)return false;
        if(query.type&&row.tool_type!==query.type)return false;
        if(query.kind&&row.kind!==query.kind)return false;
        if(query.diameter&&category==='tooling'&&!String(row.diameter_mm).includes(query.diameter))return false;
        return true;
      });const page=matches.slice(query.offset,query.offset+30);
      list.replaceChildren(element('p',`${matches.length.toLocaleString()} matching ${labels[category].toLowerCase()} records`));
      for(const row of page){const card=element('section',null,'library-card');list.append(card);
        if(category==='materials')card.append(element('h3',row.display_name),element('p',row.research_only?`${row.material_type} · Research knowledge · ${row.disposition}`:`${row.material_type} · ${(row.stock||[]).length} engineering stock sizes · ${row.active?'ACTIVE':'ARCHIVED'}`));
        if(category==='tooling')card.append(element('h3',`${row.tool_type} · Ø${displayMm(row.diameter_mm)} mm`),element('p',`${row.unit_system.toUpperCase()} · max depth ${displayMm(row.max_depth_mm)} mm · ${row.usable?'Usable':'Unavailable'}`));
        if(category==='closures')card.append(element('h3',row.display_name),element('p',`${row.model||'Model not collected'} · ${row.construction_port_name||row.construction_port_definition_id||'No construction port'} · ${row.usable?'Usable':'Unavailable: '+row.unusable_reason}`));
        if(category==='modifiers')card.append(element('h3',row.display_name),element('p',`${row.kind} · ${row.unit_system.toUpperCase()} · ${row.usable?'Usable':'Unavailable: '+row.unusable_reason}`));
        action(card,'View Detail',()=>readonlyDetail(category,row,options));
      }
      if(!matches.length)list.append(element('p',category==='closures'?'No closure or plug definitions are currently collected.':'No records match these filters.'));
      pager.replaceChildren(element('span',matches.length?`${query.offset+1}–${Math.min(query.offset+30,matches.length)} / ${matches.length}`:'0 results'));
      if(query.offset)action(pager,'Previous page',()=>{query.offset=Math.max(0,query.offset-30);scroll[category]=0;load();});
      if(query.offset+30<matches.length)action(pager,'Next page',()=>{query.offset+=30;scroll[category]=0;load();});restoreScroll(category);
    }catch(e){if(token===generation&&current===request)list.replaceChildren(element('p',labels[category]+' failed to load: '+e.message,'error'));}};
    const update=(key,value)=>{query[key]=value;query.offset=0;scroll[category]=0;clearTimeout(timer);timer=setTimeout(load,150);};
    if(category==='tooling'){field(filters,'Tool type',query.type,value=>update('type',value),{'':'All',drill:'Drill','flat-bottom-drill':'Flat-bottom drill',spotface:'Spotface'});field(filters,'Native unit',query.unit,value=>update('unit',value),{'':'All',metric:'Metric',inch:'Inch'});field(filters,'Diameter / mm',query.diameter,value=>update('diameter',value));}
    if(category==='modifiers'){field(filters,'Modifier kind',query.kind,value=>update('kind',value),{'':'All','o-ring-groove':'O-ring groove',counterbore:'Counterbore',undercut:'Undercut'});field(filters,'Native unit',query.unit,value=>update('unit',value),{'':'All',metric:'Metric',inch:'Inch'});}
    const search=field(filters,'Search '+labels[category],query.q,value=>update('q',value));search.oninput=()=>update('q',search.value);await load();
  }

  function library(options={}){
    const category=options.entryCategory||'home';
    if(category==='materials'&&options.recordId)return readonlyDetail(category,{id:options.recordId,display_name:options.recordId,research_only:true},options);
    if(category==='cartridges'&&options.recordId)return cartridgeDetail({id:options.recordId,model:options.recordId,manufacturer:''},options);
    if(category==='home')return home();
    if(category==='cavities')return cavities(options);
    if(category==='external-ports')return externalPorts(options);
    if(category==='cartridges')return cartridges(options);
    if(category==='threads')return threads(options);
    if(['materials','tooling','closures','modifiers'].includes(category))return readonlyCategory(category,options);
    throw Error('Unknown Engineering Library category: '+category);
  }
  return library;
}
