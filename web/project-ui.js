import {displayIdentity,displayReviewName} from './presentation.js';

export function projectUI(ctx){
  const {$,element,field,action,post,get,change,select,notice}=ctx;
  const dialog=$('workflow-dialog'),content=$('workflow-content');
  const open=title=>{$('workflow-title').textContent=title;content.replaceChildren();$('workflow-error').textContent='';if(!dialog.open)dialog.showModal();};
  const guard=fn=>async()=>{try{await fn();}catch(e){$('workflow-error').textContent=e.message;}};

  $('project-import').onclick=()=>{
    open('Import PMC Project JSON');
    content.append(element('p','Import accepts schema 2 project state with SQLite engineering IDs. Legacy projects must be converted with the operator migration command first.'));
    const input=element('input');input.type='file';input.accept='.json,.pmc.json';input.setAttribute('aria-label','PMC project file');content.append(input);
    input.onchange=guard(async()=>{
      const file=input.files[0];if(!file)return;if(file.size>8000000)throw Error('Project JSON exceeds 8 MB.');
      const inspection=await post('/api/import-project',JSON.parse(await file.text()));
      const box=element('section',null,'library-card');box.append(element('h3',inspection.design.name));
      for(const [key,value] of Object.entries(inspection.summary))box.append(element('p',`${key.replaceAll('_',' ')}: ${typeof value==='object'?JSON.stringify(value):value}`));
      if(inspection.missing_assets.length)box.append(element('p','Missing local schematic files: '+inspection.missing_assets.map(a=>a.name||a).join(', ')));
      action(box,'Use imported draft',()=>{if(!ctx.newProject(inspection.design,inspection.engineering?.definitions||{}))return;dialog.close();notice('Imported editable draft. Validate runs exact engineering checks.');});content.append(box);
    });
  };

  $('project-export').onclick=async()=>{try{const data=await post('/api/export-project',get());const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=element('a');a.href=url;a.download=data.name.replace(/[^a-zA-Z0-9_-]/g,'_')+'.pmc.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('Editable project state exported. Engineering definitions remain in SQLite.');}catch(e){notice(e.message,true);}};

  function reviews(){
    open('Engineering Review');const d=get(),intent=d.schematic_intent;
    content.append(element('p',`Origin: ${d.origin?.method||'unknown'} · ${d.origin?.provider||'No provider specified'} · ${d.origin?.model||'No model specified'}.`));
    const openItems=(d.review_items||[]).filter(x=>x.status==='open');content.append(element('h3',`${openItems.length} open project decisions · ${intent?.components.length||0} schematic components`));
    action(content,'Add review item',()=>{change(()=>{d.review_items??=[];let i=1;while(d.review_items.some(r=>r.id==='REVIEW_'+i))i++;d.review_items.push({id:'REVIEW_'+i,kind:'assumption',subject:'project',description:'Describe the engineering assumption to review',proposed_value:'',severity:'review',status:'open',resolution:''});});reviews();});
    for(const r of d.review_items||[]){
      const card=element('section',null,'library-card');card.append(element('h3',`${displayReviewName(r.id)} · ${r.status}`),element('p',`Subject: ${displayIdentity(d,r.subject||'project')}`));content.append(card);
      for(const [key,label]of [['description','Decision needed'],['proposed_value','Proposed value']])field(card,label,r[key],v=>change(()=>r[key]=v));
      field(card,'Severity',r.severity,v=>change(()=>r.severity=v),{review:'Review required',blocking:'Blocking uncertainty'});
      let note=r.resolution;field(card,'Engineering decision',note,v=>note=v);
      const decide=status=>{if(!note?.trim()){$('workflow-error').textContent='Enter the engineering decision before closing this item.';return;}change(()=>{r.status=status;r.resolution=note;});reviews();};
      action(card,'Accept assumption',()=>decide('accepted'));action(card,'Mark resolved',()=>decide('resolved'));action(card,'Reopen',()=>{change(()=>r.status='open');reviews();});
      if(d.features.some(f=>f.id===r.subject))action(card,'Inspect placement',()=>{select(r.subject);dialog.close();});
      const advanced=element('details');advanced.append(element('summary','Advanced / Developer information'),element('p',`Review ID: ${r.id} · Subject ID: ${r.subject||'project'}`));card.append(advanced);
    }
    for(const c of intent?.components||[]){
      const card=element('section',null,'library-card');content.append(card);card.append(element('h3',c.id),element('p',c.function||'Schematic component'));
      field(card,'Placement · '+c.id,c.placement_id||'',v=>change(()=>{c.placement_id=v||null;c.cavity_id=v?(d.features.find(f=>f.id===v)?.cavity_id||null):null;}),{'':'Not implemented',...Object.fromEntries(d.features.filter(f=>f.kind==='cavity').map(f=>[f.id,f.id]))});
      for(const [port,net]of Object.entries(c.interface_nets||{}))field(card,`${c.id} port ${port}`,net,v=>change(()=>c.interface_nets[port]=v),Object.fromEntries(d.nets.map(n=>[n.id,n.id])));
      if(c.placement_id)action(card,'Inspect placement',()=>{select(c.placement_id);dialog.close();});
    }
  }
  $('review-open').onclick=reviews;
}
