// The full native record remains attached; this editor never rebuilds it from a flat form.
export function structuredFields(ctx,parent,value,path='Native record',onEdit=()=>{}){
  const {element,field,action}=ctx;
  for(const [key,current] of Object.entries(value)){
    const label=path+' / '+key;
    if(current!==null&&typeof current==='object'){
      const section=element('details');section.append(element('summary',key+(Array.isArray(current)?` · ${current.length} records`:'')));parent.append(section);
      structuredFields(ctx,section,current,label,onEdit);
      if(Array.isArray(value))action(section,'Remove this record',()=>{value.splice(Number(key),1);onEdit();parent.replaceChildren();structuredFields(ctx,parent,value,path,onEdit);});
      if(Array.isArray(current)&&current.length&&typeof current[0]==='object')action(section,'Duplicate last '+key,()=>{current.push(structuredClone(current.at(-1)));onEdit();section.replaceChildren(element('summary',key));structuredFields(ctx,section,current,label,onEdit);});
    }else if(typeof current==='boolean')field(parent,label,String(current),v=>{value[key]=v==='true';onEdit();},{'true':'True','false':'False'});
    else field(parent,label,current??'',v=>{value[key]=v;if(key==='value'&&value.unit){if(['mm','inch','in'].includes(value.unit))value.mm=v*(value.unit==='mm'?1:25.4);value.raw=String(v);}onEdit();},null,typeof current==='number');
  }
}

export function libraryUI(ctx,{open,editor,insert}){
  const {$,element,field,action,api,post,notice,get,change}=ctx,content=$('workflow-content');
  const guard=fn=>async()=>{try{await fn();$('workflow-error').textContent='';}catch(e){$('workflow-error').textContent=e.message;}};
  let generation=0;
  return async function library(){
    const token=++generation;open('Cavity Library · PMC + MDTools 930');
    content.append(element('p','Search the converted catalog in its native units. Projects embed complete records and fixed revisions. New edits create PMC revisions; source data remains unchanged.'));
    const tabs=element('div',null,'action-row');content.append(tabs);
    const filters=element('div',null,'editor-grid');content.append(filters);const query={q:'',unit:'',kind:'cavity',family:'',manufacturer:'',cavity_type:'',thread:'',offset:0,limit:30};
    let mode='converted',showDeleted=false,timer;
    const list=element('div',null,'library-list'),pager=element('div',null,'action-row');
    const load=guard(async()=>{
      const request=++generation;list.replaceChildren(element('p','Loading catalog…'));pager.replaceChildren();
      if(mode==='converted'){
        const result=await api('/api/catalog?'+new URLSearchParams(query));if(request!==generation)return;
        list.replaceChildren(element('p',`${result.total.toLocaleString()} matching ${query.kind} records · ${result.source}`));
        if(!result.available)list.append(element('p','Converted library directory is unavailable. Pinned project definitions remain usable.'));
        for(const row of result.items){const card=element('section',null,'library-card');list.append(card);card.append(element('h3',row.name),element('p',`${row.manufacturer} · ${row.unit.toUpperCase()} · ${row.cavity_type}\n${row.thread}\n${row.id}`));
          action(card,'Inspect full native record',guard(async()=>{const record=await api('/api/catalog/record?'+new URLSearchParams({id:row.id}));open(row.name+' · native record');content.append(element('p',`${row.unit} · SHA-256 ${record.sha256} · source inspection; use Edit to create a PMC revision.`));const pre=element('pre',JSON.stringify(record,null,2));pre.className='native-inspection';content.append(pre);action(content,'Back to library',library);}));
          if(row.kind==='assembly_envelope'){
            card.append(element('p','Independent assembly envelope. Source shape type is not a cartridge relationship or a body/service role.'));
            action(card,'Associate boundary with a project cavity',guard(async()=>{
              open('Assign assembly envelope · '+row.name);content.append(element('p','Choose the cavity, boundary role and supported height explicitly. This association is your engineering decision; the source does not link it to a cavity. Height 0 retains a planar region.'));
              let definition_id='',category='',height=0,decision='';
              field(content,'Project cavity definition','',v=>definition_id=v,{'':'Choose a cavity',...Object.fromEntries(get().library.map(d=>[d.id,d.label]))});
              field(content,'Boundary role','',v=>category=v,{'':'Choose a meaning','mounting-footprint':'Mounting footprint','external-body':'External body',service:'Service clearance',tool:'Tool access'});
              field(content,'Confirmed boundary height / mm',0,v=>height=v,null,true);field(content,'Association source / engineering decision','',v=>decision=v);
              action(content,'Apply boundary to draft',guard(async()=>{const baseline=JSON.stringify(get());const design=await post('/api/assign-boundary',{design:get(),definition_id,source_id:row.id,category,height,decision});if(JSON.stringify(get())!==baseline)throw Error('Draft changed while assigning boundary; retry.');change(()=>{Object.assign(get(),design);});$('workflow-dialog').close();notice('Source envelope retained and explicit association added. Review orientation and run exact validation.');}));
            }));
          }
          if(row.kind==='cavity'){
            action(card,'Insert draft cavity',guard(async()=>insert(await api('/api/catalog/definition?'+new URLSearchParams({id:row.id})))));
            action(card,'Edit / create PMC revision',guard(async()=>editor(await api('/api/catalog/definition?'+new URLSearchParams({id:row.id})))));action(card,'Duplicate',guard(async()=>{const copy=await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));copy.id='COPY_'+Date.now().toString(36);copy.label+=' copy';copy.revision='PMC-1';editor(copy);}));action(card,row.deleted?'Restore':'Delete',guard(async()=>{await post('/api/library/visibility',{id:row.pmc_id,deleted:!row.deleted});load();}));
          }else {if(row.kind==='footprint'){card.append(element('p','Footprint stays a separate record within its parent definition.'));const parent=async()=>{const r=await api('/api/catalog/record?'+new URLSearchParams({id:row.id}));return api('/api/catalog/definition?'+new URLSearchParams({id:r.record.source_identity.cavity_ref}));};action(card,'Insert parent footprint',guard(async()=>insert(await parent())));action(card,'Edit footprint in parent',guard(async()=>editor(await parent())));action(card,'Duplicate footprint family',guard(async()=>{const copy=await parent();copy.id='COPY_'+Date.now().toString(36);copy.label+=' copy';editor(copy);}));action(card,row.deleted?'Restore':'Delete',guard(async()=>{await post('/api/library/visibility',{id:row.pmc_id,deleted:!row.deleted});load();}));}action(card,'Pin engineering record to project',guard(async()=>{const resource=await api('/api/catalog/resource?'+new URLSearchParams({id:row.id}));change(()=>{get().library_resources??=[];if(!get().library_resources.some(r=>r.id===resource.id))get().library_resources.push(resource);});notice('Pinned '+row.id+' to the editable project.');}));}
        }
        if(query.offset>0)action(pager,'Previous page',()=>{query.offset=Math.max(0,query.offset-query.limit);load();});
        pager.append(element('span',`${query.offset+1}–${Math.min(query.offset+query.limit,result.total)} / ${result.total}`));
        if(query.offset+query.limit<result.total)action(pager,'Next page',()=>{query.offset+=query.limit;load();});
      }else{
        const entries=await api('/api/library?include_deleted=true');for(const definition of get().library)if(!entries.some(e=>JSON.stringify(e.definition)===JSON.stringify(definition)))entries.push({definition,preferred:true,deleted:false});if(request!==generation)return;
        list.replaceChildren();for(const item of entries.filter(x=>(showDeleted||!x.deleted)&&x.preferred&&JSON.stringify(x.definition).toLowerCase().includes(query.q.toLowerCase()))){
          const def=item.definition,card=element('section',null,'library-card');list.append(card);card.append(element('h3',def.label),element('p',`${def.manufacturer} · ${def.id} · revision ${def.revision} · ${item.deleted?'Deleted from catalog':def.provenance}`));
          if(!item.deleted)action(card,'Insert cavity',()=>insert(def));action(card,'Edit revision',()=>editor(def));
          action(card,'Duplicate definition',()=>{const copy=structuredClone(def);copy.id='COPY_'+Date.now().toString(36);copy.label+=' copy';copy.revision='1';editor(copy);});
          action(card,item.deleted?'Restore to catalog':'Delete from catalog',guard(async()=>{await post('/api/library/visibility',{id:def.id,deleted:!item.deleted});await load();}));
        }
      }
    });
    action(tabs,'Converted MDTools catalog',()=>{mode='converted';query.offset=0;load();});action(tabs,'PMC revisions / project library',()=>{mode='pmc';load();});
    action(tabs,'Show / hide deleted',()=>{showDeleted=!showDeleted;query.include_deleted=String(showDeleted);load();});
    action(tabs,'Provisional mapping report',guard(async()=>{const r=await api('/api/catalog/mapping-report');open('Geometry mapping review list');content.append(element('p',`${r.provisional} provisional / ${r.total} cavities · ${r.scope}`));for(const row of r.items){const card=element('section',null,'library-card');card.append(element('h3',row.name),element('p',row.id),...row.reasons.map(x=>element('p',x)));action(card,'Inspect mapping',guard(async()=>editor(await api('/api/catalog/definition?'+new URLSearchParams({id:row.id})))));content.append(card);}}));
    action(tabs,'Find compatible cavities',guard(async()=>{const entries=await api('/api/library');open('Cartridge → compatible cavities');const results=element('div');const search=field(content,'Cartridge model','',()=>{});const render=()=>{results.replaceChildren();let count=0;for(const e of entries.filter(x=>x.preferred&&!x.deleted)){const d=e.definition;for(const c of d.compatible_cartridges||[])if(c.status!=='unconfirmed'&&c.model.toLowerCase().includes(search.value.toLowerCase())){count++;const card=element('section',null,'library-card');card.append(element('h3',c.model+' → '+d.label),element('p',c.status+' · '+c.source));action(card,'Insert compatible cavity',()=>insert(d));results.append(card);}}if(!count)results.append(element('p','No documented match in the local catalog. Select a cavity manually and keep compatibility under engineering review.'));};search.oninput=render;content.append(results);render();}));
    action(tabs,'Materials / manufacturing rules',guard(async()=>{const resources=await api('/api/catalog/resources');open('Shared engineering resources');for(const resource of resources){const card=element('section',null,'library-card');card.append(element('h3',resource.kind));const pre=element('pre',JSON.stringify(resource.record,null,2));pre.className='native-inspection';card.append(pre);action(card,'Pin resource to project',()=>{change(()=>{get().library_resources??=[];if(!get().library_resources.some(r=>r.id===resource.id))get().library_resources.push(resource);});notice('Resource pinned as imported engineering guidance. Active validation rules are not silently changed.');});content.append(card);}}));
    action(tabs,'Create custom cavity',()=>{editor({id:'CUSTOM_'+Date.now().toString(36),label:'New custom cavity',manufacturer:'PMC Custom',source:'PMC custom definition · provisional dimensions',revision:'1',provenance:'candidate',demo_only:false,thread_note:'',valve_function:'Unspecified',machining_notes:'',cartridge_models:[],stages:[{start:0,end:30,diameter:16}],zones:[{id:'port1',start:20,end:30,diameter:16}],clearance_diameter:24,clearance_height:30,tooling:[],cutting_primitives:[],native:null,catalog_id:''});});
    const update=(key,v)=>{query[key]=v;query.offset=0;clearTimeout(timer);timer=setTimeout(load,180);};
    const searchInput=field(filters,'Search model or cavity',query.q,v=>update('q',v));searchInput.oninput=()=>update('q',searchInput.value);field(filters,'Native units',query.unit,v=>update('unit',v),{'':'All units',metric:'Metric · mm',inch:'Inch · native inches'});
    field(filters,'Record type',query.kind,v=>{const [kind,family]=v.split(':');query.family=family||'';update('kind',kind);},{cavity:'Cavities',footprint:'Footprints',o_ring_groove:'O-ring grooves',undercut:'Undercuts','tool:drill':'Drill tools','tool:flat_bottom_drill':'Flat-bottom drill tools','tool:spot_face':'Spot-face tools',material_stock:'Material stock',assembly_envelope:'Assembly envelopes'});
    for(const [key,label]of [['manufacturer','Manufacturer / library'],['cavity_type','Cavity type'],['thread','Thread specification']]){const input=field(filters,label,'',v=>update(key,v));input.oninput=()=>update(key,input.value);}
    content.append(list,pager);await load();
  };
}
