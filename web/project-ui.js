export function projectUI(ctx){
  const {$,element,field,action,post,get,change,set,select,notice,editDefinition}=ctx;
  const dialog=$('workflow-dialog'),content=$('workflow-content');
  const open=title=>{$('workflow-title').textContent=title;content.replaceChildren();$('workflow-error').textContent='';if(!dialog.open)dialog.showModal();};
  const guard=fn=>async()=>{try{await fn();}catch(e){$('workflow-error').textContent=e.message;}};
  $('project-import').onclick=()=>{
    open('Import PMC Project JSON');
    content.append(element('p','AI and manual work use the same editable project. Import replaces the draft with Undo available; Save & Validate commits it. STEP is a downstream manufacturing artifact.'));
    const input=element('input');input.type='file';input.accept='.json,.pmc.json';input.setAttribute('aria-label','PMC project file');content.append(input);
    input.onchange=guard(async()=>{
      const file=input.files[0];if(!file)return;if(file.size>8000000)throw Error('Project JSON exceeds 8 MB.');
      const inspection=await post('/api/import-project',JSON.parse(await file.text()));
      const box=element('section',null,'library-card');box.append(element('h3',inspection.design.name));
      for(const [key,value] of Object.entries(inspection.summary))box.append(element('p',`${key.replaceAll('_',' ')}: ${typeof value==='object'?JSON.stringify(value):value}`));
      if(inspection.missing_assets.length)box.append(element('p','Missing local schematic files: '+inspection.missing_assets.map(a=>a.name||a).join(', ')));
      action(box,'Use imported draft',()=>{change(()=>set(inspection.design));dialog.close();notice('Imported editable draft. Resolve Engineering Review items, then Save & Validate.');});content.append(box);
    });
  };
  $('project-export').onclick=async()=>{try{const data=await post('/api/export-project',get());const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=element('a');a.href=url;a.download=data.name.replace(/[^a-zA-Z0-9_-]/g,'_')+'.pmc.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('Editable project exported, including pinned library definitions and review decisions. Schematic binaries stay in local assets.');}catch(e){notice(e.message,true);}};
  function reviews(){
    open('Engineering Review');const d=get();
    content.append(element('p',`Origin: ${d.origin?.method||'unknown'} · ${d.origin?.provider||'No provider specified'} · ${d.origin?.model||'No model specified'}. Decisions stay in the project regardless of which AI or engineer created it.`));
    const openItems=(d.review_items||[]).filter(x=>x.status==='open');content.append(element('h3',`${openItems.length} open decisions · ${d.components.filter(c=>c.status==='unconfirmed').length} unconfirmed components`));
    action(content,'Add review item',()=>{change(()=>{d.review_items??=[];let i=1;while(d.review_items.some(r=>r.id==='REVIEW_'+i))i++;d.review_items.push({id:'REVIEW_'+i,kind:'assumption',subject:'project',description:'Describe the engineering assumption to review',proposed_value:'',severity:'review',status:'open',resolution:''});});reviews();});
    for(const r of d.review_items||[]){
      const card=element('section',null,'library-card');card.append(element('h3',`${r.id} · ${r.status}`));content.append(card);
      for(const [key,label]of [['subject','Subject'],['description','Decision needed'],['proposed_value','Proposed value']])field(card,label+' · '+r.id,r[key],v=>change(()=>r[key]=v));
      field(card,'Severity · '+r.id,r.severity,v=>change(()=>r.severity=v),{review:'Review required',blocking:'Blocking uncertainty'});
      let note=r.resolution;field(card,'Engineering decision · '+r.id,note,v=>note=v);
      const decide=status=>{if(!note?.trim()){$('workflow-error').textContent='Enter the engineering decision before closing this item.';return;}change(()=>{r.status=status;r.resolution=note;});reviews();};
      action(card,'Accept assumption',()=>decide('accepted'));action(card,'Mark resolved',()=>decide('resolved'));action(card,'Reopen',()=>{change(()=>r.status='open');reviews();});
      if(d.features.some(f=>f.id===r.subject))action(card,'Inspect feature',()=>{select(r.subject);dialog.close();});
    }
    for(const c of d.components){const card=element('section',null,'library-card');content.append(card);card.append(element('h3',`${c.id} · ${c.status}`),element('p',c.function));
      field(card,'Component model · '+c.id,c.cartridge_model,v=>change(()=>{c.cartridge_model=v;c.status='unconfirmed';}));
      field(card,'Placement · '+c.id,c.feature_id||'',v=>change(()=>{c.feature_id=v||null;c.status='unconfirmed';}),{'':'Not placed',...Object.fromEntries(d.features.filter(f=>f.kind==='cavity').map(f=>[f.id,f.id]))});
      for(const [port,net]of Object.entries(c.ports))field(card,`${c.id} port ${port}`,net,v=>change(()=>{c.ports[port]=v;c.status='unconfirmed';}),Object.fromEntries(d.nets.map(n=>[n.id,n.id])));
      action(card,'Confirm against placed cavity',()=>{const f=d.features.find(f=>f.id===c.feature_id);if(!f||f.suppressed||f.kind!=='cavity'){$('workflow-error').textContent='Choose an active placed cavity first.';return;}if(JSON.stringify(Object.entries(c.ports).sort())!==JSON.stringify(Object.entries(f.circuits).sort())){$('workflow-error').textContent='Schematic port mapping differs from placed interfaces. Review the mappings first.';return;}change(()=>{c.cavity_definition=f.definition;c.cartridge_model=f.cartridge_model;c.status='confirmed';});reviews();});
      if(c.feature_id)action(card,'Inspect placement',()=>{select(c.feature_id);dialog.close();});
    }
    for(const def of d.library.filter(x=>x.native)){const card=element('section',null,'library-card');card.append(element('h3',def.label),element('p',`Geometry: ${def.native.geometry_status} · Machining: ${def.native.machining_status}`),...def.native.geometry_notes.map(s=>element('p',s)));action(card,'Edit pinned definition',()=>editDefinition(def));content.append(card);}
  }
  $('review-open').onclick=reviews;
}
