import {isCavity} from './definition-role.js';
import {profileEditor} from './profile.js';

export function libraryUI(ctx,{open,insert,onCustomSaved=()=>{}}){
  const {$,element,field,action,api,post}=ctx,content=$('workflow-content');
  const guard=fn=>async()=>{try{await fn();$('workflow-error').textContent='';}catch(e){$('workflow-error').textContent=e.message;}};
  let generation=0;
  const blank=()=>({id:'custom_pending',label:'Custom cavity',family:'Custom',unit_system:ctx.get().project_context||'metric',manufacturer:'',thread_note:'',
    stages:[{start:0,end:20,diameter:20}],zones:[{id:'port1',start:10,end:18,diameter:18,offset_u:0,offset_v:0,clip_to_cut:true}],
    clearance_diameter:24,clearance_height:20,cutting_primitives:[],boundaries:[],machining:[],usable:true,unusable_reason:'',active:true,kind:'cavity'});
  const rowsField=(parent,label,definition,key,rerender)=>{
    const wrap=element('label',label,'field'),input=element('textarea');input.setAttribute('aria-label',label);input.spellcheck=false;input.value=JSON.stringify(definition[key]||[],null,2);
    input.onchange=()=>{try{const value=JSON.parse(input.value);if(!Array.isArray(value))throw Error('Expected a JSON array');definition[key]=value;$('workflow-error').textContent='';rerender();}catch(e){$('workflow-error').textContent=label+': '+e.message;}};wrap.append(input);parent.append(wrap);
  };
  function editCustom(source=null,backOptions={}){
    ++generation;const definition=structuredClone(source||blank());definition.id='custom_pending';definition.kind='cavity';definition.active=true;definition.usable=true;definition.unusable_reason='';
    const render=()=>{open(source?'Duplicate as Custom Cavity':'Create Custom Cavity');content.append(element('p','Saving creates a new stable SQLite cavity ID. The source/master definition and existing projects are not changed.'));
      const basics=element('section',null,'editor-grid');content.append(basics);
      field(basics,'Display name',definition.label,v=>definition.label=v);field(basics,'Engineering units',definition.unit_system,v=>definition.unit_system=v,{metric:'Metric',inch:'Inch',custom:'Custom'});
      field(basics,'Family / type',definition.family,v=>definition.family=v);field(basics,'Manufacturer',definition.manufacturer,v=>definition.manufacturer=v);
      field(basics,'Thread / note',definition.thread_note,v=>definition.thread_note=v);field(basics,'Clearance diameter / mm',definition.clearance_diameter,v=>definition.clearance_diameter=v,null,true);field(basics,'Clearance height / mm',definition.clearance_height,v=>definition.clearance_height=v,null,true);
      const data=element('details');data.open=true;data.append(element('summary','Editable engineering arrays'));content.append(data);
      rowsField(data,'Machining stages JSON',definition,'stages',render);rowsField(data,'Cutting primitives JSON',definition,'cutting_primitives',render);rowsField(data,'Hydraulic interfaces JSON',definition,'zones',render);rowsField(data,'Supported boundaries JSON',definition,'boundaries',render);rowsField(data,'Machining notes / operations JSON',definition,'machining',render);
      profileEditor(ctx,content,definition);
      const buttons=element('div',null,'action-row');content.append(buttons);action(buttons,'Save New Custom Cavity',guard(async()=>{const saved=await post('/api/catalog/custom-cavity',{definition});onCustomSaved(saved);open('Custom cavity saved');content.append(element('h3',saved.label),element('p',`${saved.id}\n${saved.unit_system.toUpperCase()} · ${saved.family||'Custom'}\nThe new record is active in the SQLite Engineering Library and can replace a placed cavity.`));action(content,'Place this cavity',()=>insert(saved));action(content,'Back to Engineering Library',()=>library(backOptions));})).classList.add('primary');action(buttons,'Cancel',()=>library(backOptions));
    };render();
  }
  function viewDefinition(definition,options={}){++generation;open('Cavity Definition · '+definition.label);content.append(element('p',`${definition.id.startsWith('custom_')||definition.id.startsWith('legacy_')?'CUSTOM / LOCAL':'PMC MASTER'} · ${definition.unit_system.toUpperCase()} · ${definition.family||'Family unspecified'}\nEngineering reference: ${definition.id}`));profileEditor(ctx,content,definition,{editable:false});const row=element('div',null,'action-row');content.append(row);action(row,options.actionLabel||'Place Cavity',()=>{(options.onSelect||insert)(definition);});action(row,'Duplicate as Custom',()=>editCustom(definition,options));action(row,'Back to Engineering Library',()=>library(options));}
  async function library(options={}){
    const openToken=++generation;open(options.title||'Engineering Library · SQLite');
    content.append(element('p','Search the runtime engineering database. A selected cavity is referenced by ID; its full definition is loaded for this session and is not embedded in the project.'));
    const createRow=element('div',null,'action-row');content.append(createRow);action(createRow,'Create Custom Cavity',()=>editCustom(null,options));
    const filters=element('div',null,'editor-grid'),list=element('div',null,'library-list'),pager=element('div',null,'action-row');content.append(filters,list,pager);
    const query={q:'',unit:ctx.get().project_context||'',kind:'cavity',family:'',manufacturer:'',thread:'',status:'all',scope:'all',offset:0,limit:30};let timer,requestGeneration=0;
    const load=async()=>{
      const request=++requestGeneration;list.replaceChildren(element('p','Loading SQLite engineering data…'));pager.replaceChildren();
      try{
        const result=await api('/api/catalog?'+new URLSearchParams(query));if(openToken!==generation||request!==requestGeneration)return;
        list.replaceChildren(element('p',`${result.total.toLocaleString()} matching cavities`));
        for(const row of result.items){
          const card=element('section',null,'library-card'),custom=row.id.startsWith('custom_')||row.id.startsWith('legacy_');list.append(card);card.append(element('h3',row.name),element('p',`${custom?'CUSTOM / LOCAL':'PMC MASTER'} · ${row.manufacturer||'Manufacturer unspecified'} · ${row.family||'Family unspecified'} · ${row.unit_system.toUpperCase()}\n${row.thread_spec||'No thread specification'}\nEngineering reference: ${row.id}`));
          if(!row.usable)card.append(element('p','Unavailable: '+row.unusable_reason,'error'));
          action(card,'View Definition',guard(async()=>{const definition=await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(!isCavity(definition))throw Error('Selected record is not a cavity.');viewDefinition(definition,options);}));
          if(row.usable)action(card,options.actionLabel||'Place Cavity',guard(async()=>{const definition=await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(!isCavity(definition))throw Error('Selected record is not a cavity.');(options.onSelect||insert)(definition);}));
        }
        if(query.offset>0)action(pager,'Previous page',()=>{query.offset=Math.max(0,query.offset-query.limit);load();});
        pager.append(element('span',result.total?`${query.offset+1}–${Math.min(query.offset+query.limit,result.total)} / ${result.total}`:'0 results'));
        if(query.offset+query.limit<result.total)action(pager,'Next page',()=>{query.offset+=query.limit;load();});
        $('workflow-error').textContent='';
      }catch(e){if(openToken!==generation||request!==requestGeneration)return;list.replaceChildren(element('p','Engineering Library failed to load: '+e.message,'error'));$('workflow-error').textContent=e.message;}
    };
    const update=(key,value)=>{query[key]=value;query.offset=0;clearTimeout(timer);timer=setTimeout(load,180);};
    const search=field(filters,'Search cavity',query.q,v=>update('q',v));search.oninput=()=>update('q',search.value);
    field(filters,'Engineering units',query.unit,v=>update('unit',v),{'':'All units',metric:'Metric',inch:'Inch',custom:'Custom'});
    field(filters,'Family / type',query.family,v=>update('family',v));field(filters,'Manufacturer',query.manufacturer,v=>update('manufacturer',v));field(filters,'Thread',query.thread,v=>update('thread',v));
    field(filters,'Library scope',query.scope,v=>update('scope',v),{all:'Master and custom',master:'PMC master',custom:'Custom / local'});
    field(filters,'Engineering availability',query.status,v=>update('status',v),{all:'Usable and unavailable',usable:'Usable only',unavailable:'Unavailable only'});
    content.append(element('p','External-port definitions are selected from Add External Port. Cartridge assignments are chosen on a placed cavity and validated by the explicit database relationship.'));
    await load();
  }
  library.viewDefinition=(definition,options={})=>viewDefinition(definition,options);
  library.duplicateAsCustom=(definition,options={})=>editCustom(definition,options);
  return library;
}
