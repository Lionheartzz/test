import {hydrateDesign} from './domain.js';
import {axes} from './kinematics.js';
import {machiningFits} from './model-machining-bounds.js';
import {uuidToken} from './crypto-utils.js';
import {engineeringName,engineeringText,unitLabel} from './engineering-labels.js';

const faces={top:'Top',bottom:'Bottom',front:'Front',back:'Back',left:'Left',right:'Right'};
const dimensions=design=>[design.block.length,design.block.width,design.block.height];
const mm=value=>String(Number(Number(value).toFixed(3)));
const readableError=error=>engineeringText(error.message).replace(/\bENG_[0-9a-f]{12,32}\b/gi,'engraving').replace(/\bMNT_[0-9a-f]{12,32}\b/gi,'mounting hole').replace(/\bthr_[A-Za-z0-9_-]+\b/gi,'thread');
const positive=(value,label,maximum=2000)=>{if(!Number.isFinite(value)||value<=0||value>maximum)throw Error(`${label} must be greater than zero and no more than ${maximum} mm.`);return value;};
function grouped(node,name){node.closest('.field')?.setAttribute('data-inspector-group',name);return node;}

export function engravingLabel(row){return `Engraving “${row.text}”`;}

export function engravingEditor(ctx,form,row){
  const {element,field,action,change,get,select}=ctx;
  const edit=(label,value,apply,group,options=null,numeric=false)=>grouped(field(form,label,value,v=>change(()=>apply(v),{kind:'machining'}),options,numeric),group);
  form.append(element('div',engravingLabel(row),'inspector-title'));
  const actions=element('div',null,'action-row');form.append(actions);
  action(actions,'Duplicate',()=>{
    const id='ENG_'+uuidToken().replaceAll('-','');
    if(change(()=>{if(get().engravings.length>=80)throw Error('This project already has the maximum of 80 engravings.');const copy=structuredClone(row),size=dimensions(get()),[u,v]=axes[row.face];copy.id=id;copy.u=Math.min(size[u],copy.u+10);copy.v=Math.min(size[v],copy.v+10);get().engravings.push(copy);},{kind:'machining'}))select(id);
  });
  action(actions,'Delete',()=>{if(change(()=>get().engravings=get().engravings.filter(value=>value.id!==row.id),{kind:'machining'}))select('block');});
  edit('Face',row.face,value=>{row.face=value;const size=dimensions(get()),[u,v]=axes[value];row.u=Math.min(row.u,size[u]);row.v=Math.min(row.v,size[v]);},'Position',faces);
  for(const [key,label,index]of [['u','Position U / mm',0],['v','Position V / mm',1]]){
    const maximum=dimensions(get())[axes[row.face][index]],input=edit(label,row[key],value=>{if(value<0||value>maximum)throw Error(`${label} must stay within this block face.`);row[key]=value;},'Position',null,true);
    input.min=0;input.max=maximum;
  }
  const text=edit('Text',row.text,value=>{if(!value.length||value.length>40)throw Error('Engraving text must contain 1–40 characters.');row.text=value;},'Marking');text.maxLength=40;text.required=true;
  edit('Text height / mm',row.text_height,value=>row.text_height=positive(value,'Text height',50),'Marking',null,true);
  edit('Engraving depth / mm',row.depth,value=>row.depth=positive(value,'Engraving depth',5),'Marking',null,true);
  edit('Rotation / degrees',row.rotation,value=>{if(value<-360||value>360)throw Error('Rotation must be between -360 and 360 degrees.');row.rotation=value;},'Marking',null,true);
}

export function blockModifierEditor(ctx,form,row){
  const {element,field,action,change,get,select}=ctx,title=row.kind==='chamfer'?'Chamfer':'Rectangular cutout';
  form.append(element('div',title,'inspector-title'));
  const actions=element('div',null,'action-row');form.append(actions);
  action(actions,'Delete',()=>{if(change(()=>get().block_modifiers=get().block_modifiers.filter(value=>value.id!==row.id),{kind:'machining'}))select('block');});
  const edit=(label,value,apply,group,options=null,numeric=false)=>grouped(field(form,label,value,next=>change(()=>{
    apply(next);if(!machiningFits(row,get().block))throw Error(`${title} must remain within the finished block. Restore the previous value or adjust its size and position.`);
  },{kind:'machining'}),options,numeric),group);
  edit('Face',row.face,value=>row.face=value,'Position',faces);
  if(row.kind==='chamfer'){edit('Size / mm',row.size,value=>row.size=positive(value,'Chamfer size',100),'Machining',null,true);return;}
  for(const [key,label]of [['u','Position U / mm'],['v','Position V / mm']])edit(label,row[key],value=>{if(value<0||value>2000)throw Error('Position must stay within the block face.');row[key]=value;},'Position',null,true);
  for(const [key,label]of [['width','Width / mm'],['height','Height / mm'],['depth','Depth / mm']])edit(label,row[key],value=>row[key]=positive(value,label,2000),'Machining',null,true);
  edit('Rotation / degrees',row.rotation,value=>{if(value<-360||value>360)throw Error('Rotation must be between -360 and 360 degrees.');row.rotation=value;},'Position',null,true);
}

function threadPicker(ctx,parent,isCurrent,onUse){
  const {element,field,action,api,notice}=ctx;
  const panel=element('details');panel.dataset.inspectorGroup='Mounting specification';
  panel.append(element('summary','Select thread…'));parent.append(panel);
  const filters=element('div'),results=element('div'),paging=element('div',null,'action-row');panel.append(filters,results,paging);
  let query='',unit='',family='',offset=0,request=0,timer=null,loaded=false;
  const current=()=>panel.isConnected&&isCurrent();
  async function load(){
    const ticket=++request;loaded=true;results.replaceChildren(element('p','Loading threads…','property-note'));paging.replaceChildren();
    try{
      const response=await api('/api/threads?'+new URLSearchParams({q:query,unit,family,usable_only:true,offset,limit:10}));
      if(ticket!==request||!current())return;
      const options=(response.families||[]).map(value=>[value,value]);familyInput.replaceChildren();
      for(const [value,label]of [['','All families'],...options]){const option=element('option',label);option.value=value;familyInput.append(option);}familyInput.value=family;
      results.replaceChildren();
      for(const row of response.items||[]){
        if(!row.usable||!row.active||!Number.isFinite(Number(row.tap_diameter_mm))||Number(row.tap_diameter_mm)<=0)continue;
        const card=element('div',null,'library-card');results.append(card);
        card.append(element('strong',engineeringName(row.display_name,'Thread')),
          element('p',[row.normalized_family||row.family,unitLabel(row.unit_system),row.nominal_size,row.pitch_tpi].filter(Boolean).join(' · '),'property-note'),
          element('p','Tap drill Ø'+mm(row.tap_diameter_mm)+' mm','property-note'));
        const use=action(card,'Use',async()=>{if(!current())return;use.disabled=true;try{await onUse(row,current);}catch(error){if(current())notice(readableError(error),true);}finally{if(current())use.disabled=false;}});
      }
      if(!results.childElementCount)results.append(element('p','No available threads match.','property-note'));
      const total=response.total||0;paging.append(element('span',total?`${offset+1}–${Math.min(offset+10,total)} of ${total}`:'0 threads','property-note'));
      if(offset)action(paging,'Previous',()=>{offset=Math.max(0,offset-10);load();});
      if(offset+10<total)action(paging,'Next',()=>{offset+=10;load();});
    }catch(error){if(ticket!==request||!current())return;results.replaceChildren(element('p','Threads could not be loaded. '+readableError(error),'property-note'));action(results,'Retry',load);}
  }
  const update=()=>{++request;offset=0;clearTimeout(timer);results.replaceChildren(element('p','Searching threads…','property-note'));paging.replaceChildren();timer=setTimeout(()=>{if(current())load();},180);};
  const search=field(filters,'Search threads',query,value=>{query=value;update();});search.type='search';search.oninput=()=>{query=search.value;update();};
  field(filters,'Units',unit,value=>{unit=value;update();},{'':'All units',metric:'Metric',inch:'Inch'});
  const familyInput=field(filters,'Family',family,value=>{family=value;update();},{'':'All families'});
  panel.addEventListener('toggle',()=>{if(panel.open&&!loaded)load();});
  return ()=>{panel.open=true;if(!loaded)load();};
}

export function mountingEditor(ctx,form,feature){
  const {get,field,element,action,change,post,select,notice}=ctx;
  const owner=get(),id=feature.id;
  const current=()=>get()===owner&&get().features.includes(feature)&&ctx.selection()===id&&form.isConnected;
  const thread=get().threads?.find(row=>row.id===feature.thread_definition_id),threaded=feature.mounting_mode==='threaded';
  const edit=(label,value,apply,options=null,numeric=false)=>grouped(field(form,label,value,v=>change(()=>apply(v)),options,numeric),'Mounting specification');
  async function replaceMode(mode,definition,isCurrent=current){
    if(!isCurrent())return;
    const baseline=JSON.stringify(owner),next=structuredClone(owner),hole=next.features.find(row=>row.id===id);
    if(mode==='threaded'){
      if(!definition?.active||!definition?.usable)throw Error('Select an available thread definition first.');
      positive(Number(definition.tap_diameter_mm),'Tap drill');
      hole.mounting_mode='threaded';hole.thread_definition_id=definition.id;hole.diameter=null;
      hole.thread_depth=hole.through?hole.depth:Math.min(hole.thread_depth||16,hole.depth);
    }else{
      hole.diameter=positive(Number(definition?.tap_diameter_mm),'Loaded tap drill');
      hole.mounting_mode='plain';hole.thread_definition_id=null;hole.thread_depth=null;
    }
    const checked=await post('/api/check-design',next);
    if(!isCurrent()||get()!==owner||JSON.stringify(owner)!==baseline)throw Error('Draft changed while updating the mounting hole. Select the hole and retry.');
    const threads=Object.fromEntries([...(owner.threads||[]),...(definition?[definition]:[])].map(row=>[row.id,row]));
    const definitions=Object.fromEntries((owner.library||[]).map(row=>[row.id,row]));
    if(change(()=>ctx.set(hydrateDesign(checked,definitions,threads))))select(id);
  }
  let choose;
  const mode=grouped(field(form,'Hole type',threaded?'threaded':'plain',value=>{
    if(value===(threaded?'threaded':'plain'))return;
    mode.value=threaded?'threaded':'plain';
    if(value==='threaded')choose();
    else replaceMode('plain',thread).catch(error=>{if(current())notice(readableError(error),true);});
  },{plain:'Plain hole',threaded:'Threaded hole'}),'Mounting specification');
  if(threaded){
    const info=element('p',`Thread: ${engineeringName(thread?.display_name,'Selected thread')}\nTap drill: ${thread?.tap_diameter_mm?'Ø'+mm(thread.tap_diameter_mm)+' mm':'Not loaded'}`,'property-note');info.dataset.inspectorGroup='Mounting specification';form.append(info);
    const button=action(form,'Change thread…',()=>choose());button.dataset.inspectorGroup='Mounting specification';
  }else edit('Diameter / mm',feature.diameter,value=>feature.diameter=positive(value,'Diameter'),null,true);
  choose=threadPicker(ctx,form,current,(row,isCurrent)=>replaceMode('threaded',row,isCurrent));
  edit('Through hole',String(!!feature.through),value=>{
    feature.through=value==='true';
    if(feature.through){feature.tip_angle=180;feature.depth=dimensions(get())[axes[feature.face][2]];if(threaded)feature.thread_depth=feature.depth;}
  },{false:'Blind',true:'Through'});
  if(!feature.through)edit(threaded?'Tap-drill depth / mm':'Drill depth / mm',feature.depth,value=>{
    positive(value,'Drill depth');if(threaded&&value<feature.thread_depth)throw Error('Drill depth cannot be less than thread depth.');feature.depth=value;
  },null,true);
  else{const depth=element('p','Through depth: '+mm(feature.depth)+' mm','property-note');depth.dataset.inspectorGroup='Mounting specification';form.append(depth);}
  if(threaded)edit('Thread depth / mm',feature.thread_depth,value=>feature.thread_depth=positive(value,'Thread depth',feature.depth),null,true);
  if(!feature.through)edit('Drill point angle / degrees',feature.tip_angle,value=>{if(value<60||value>180)throw Error('Drill point angle must be between 60 and 180 degrees.');feature.tip_angle=value;},null,true);
  const note=element('p',threaded?'Tap-drill diameter follows the selected thread definition. CAD uses the defined bore without helical thread faces.':'Plain non-hydraulic mounting cut.','property-note');note.dataset.inspectorGroup='Mounting specification';form.append(note);
}
