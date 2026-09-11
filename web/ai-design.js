// Hydraulic understanding is reviewed here; this module never mutates the CAD draft.
export function aiDesign(ctx,open){
  const {$,element,field,action,api,post,get,state}=ctx,content=$('workflow-content');
  let active=null,inputs=null,run=null,dirty=false,pending=false,provider='mock-safe',source=null,providers=[],generation=0;
  const fresh=()=>({title:'New hydraulic analysis',documents:[],engineering_requirements:'',project_context:get()?.project_context||'metric',linked_project_id:state()?.project_id||null});
  const here=()=>$('workflow-dialog').open&&$('workflow-title').textContent.startsWith('AI Design');
  const guard=fn=>async()=>{if(pending)return;pending=true;content.querySelectorAll('button,input,select,textarea').forEach(x=>x.disabled=true);$('workflow-error').textContent='';try{await fn();}catch(e){$('workflow-error').textContent=e.message;}finally{pending=false;if(here())content.querySelectorAll('button,input,select,textarea').forEach(x=>x.disabled=false);}};
  const touched=()=>{dirty=true;const status=content.querySelector('.ai-save-state');if(status)status.textContent='Inputs changed · save before analysis';};
  async function save(){
    const signature=JSON.stringify(inputs),result=await post('/api/ai-design/tasks',{inputs,task_id:active?.id||null,expected_revision:active?.revision||null});
    active=result;if(JSON.stringify(inputs)===signature){inputs=structuredClone(result.inputs);dirty=false;}
    return result;
  }
  function addAsset(asset){if(!inputs.documents.some(d=>d.asset.sha256===asset.sha256)){inputs.documents.push({id:'DOC_'+crypto.randomUUID().replaceAll('-',''),asset,page_count:asset.media_type.startsWith('image/')?1:null});touched();}}
  async function upload(file){
    if(!['application/pdf','image/png','image/jpeg'].includes(file.type))throw Error('Use PDF, PNG or JPEG schematic files.');
    if(file.size>20_000_000)throw Error('Each document must be at most 20 MB.');
    const asset=await api('/api/assets',{method:'POST',headers:{'Content-Type':file.type,'X-File-Name':encodeURIComponent(file.name),'X-PMC-Request':'local-console'},body:file});addAsset(asset);
  }
  async function library(){
    if(dirty&&!confirm('Leave these unsaved analysis inputs?'))return;
    const token=++generation;open('AI Design · Analysis workspaces');
    content.append(element('p','Understand a hydraulic circuit before deciding how to build its manifold. Documents, original requirements, model interpretation and engineer review stay together.'));
    const loading=element('p','Loading local analyses and provider capabilities…','loading-state');content.append(loading);
    const [rows,available]=await Promise.all([api('/api/ai-design/tasks'),api('/api/ai-design/providers')]);if(!here()||token!==generation)return;providers=available;loading.remove();
    action(content,'New analysis',()=>{active=null;inputs=fresh();run=null;dirty=false;source=null;editor();});
    for(const row of rows){const card=element('section',null,'library-card');content.append(card);card.append(element('h3',row.title),element('p',`${row.documents} documents · ${row.latest_run?.status||'Not analyzed'}${row.stale?' · inputs changed':''}`));action(card,'Open analysis',guard(async()=>{active=await api('/api/ai-design/tasks/'+row.id);inputs=structuredClone(active.inputs);dirty=false;source=null;run=active.latest_run?await api(`/api/ai-design/tasks/${row.id}/runs/${active.latest_run.id}`):null;if(here())editor();}));}
    if(!rows.length)content.append(element('p','No analyses yet. Start with a schematic and your engineering requirements.'));
  }
  function editor(){
    if(!$('workflow-dialog').open)open('AI Design · Hydraulic understanding');else if(!here())return;
    ++generation;open('AI Design · Hydraulic understanding');content.classList.add('ai-content');
    const nav=element('div',null,'action-row');content.append(nav);action(nav,'All analyses',library);
    nav.append(element('span',dirty?'Inputs changed · save before analysis':active?'Saved locally':'New analysis · not saved','ai-save-state'));
    const inputPanel=element('section',null,'ai-inputs');content.append(inputPanel);
    field(inputPanel,'Analysis title',inputs.title,v=>{inputs.title=v;touched();});
    field(inputPanel,'Engineering unit context',inputs.project_context,v=>{inputs.project_context=v;touched();},{metric:'Metric',inch:'Inch'});
    inputPanel.append(element('h3','Schematic documents'));
    const uploadInput=element('input');uploadInput.type='file';uploadInput.multiple=true;uploadInput.accept='.pdf,.png,.jpg,.jpeg';uploadInput.setAttribute('aria-label','Upload schematic documents');inputPanel.append(uploadInput);
    uploadInput.onchange=guard(async()=>{try{for(const file of uploadInput.files)await upload(file);}finally{if(here())editor();}});
    const documents=element('div',null,'ai-document-list');inputPanel.append(documents);
    for(const document of inputs.documents){const row=element('div',null,'action-row');row.append(element('span',document.asset.name+' · '+(document.asset.size/1024).toFixed(1)+' KB'));action(row,'View '+document.asset.name,()=>{source={document};renderSource();});action(row,'Remove '+document.asset.name,()=>{inputs.documents=inputs.documents.filter(d=>d.id!==document.id);touched();editor();});documents.append(row);}
    const extras=element('div',null,'action-row');inputPanel.append(extras);
    action(extras,'Use synthetic sample schematic',guard(async()=>{const response=await fetch('/ai-demo.png');if(!response.ok)throw Error('Sample schematic is unavailable.');await upload(new File([await response.blob()],'PMC synthetic example.png',{type:'image/png'}));provider='mock-example';if(here())editor();}));
    if(get()?.schematics?.length)action(extras,'Use current project schematics',()=>{for(const a of get().schematics)addAsset(structuredClone(a));editor();});
    const label=element('label','Engineering requirements · original instruction','field'),requirements=element('textarea');requirements.rows=7;requirements.value=inputs.engineering_requirements;requirements.setAttribute('aria-label','Engineering requirements');requirements.placeholder='Use SUN cartridges where possible.\nP and T on bottom. A and B on left.\nMaximum block width 150 mm.\nWorking pressure 250 bar. Maximum flow 60 L/min.\nAdd selection, machining, access or interpretation requirements here.';requirements.oninput=()=>{inputs.engineering_requirements=requirements.value;touched();};label.append(requirements);inputPanel.append(label);
    inputPanel.append(element('p','Your original wording is preserved. Proposed interpretations are reviewed separately and are not applied to geometry.','property-note'));
    field(inputPanel,'Analysis provider / model',provider,v=>provider=v,Object.fromEntries(providers.map(p=>[p.id,`${p.is_mock?'Local mock':'Provider'} · ${p.provider} / ${p.model}`])));
    inputPanel.append(element('p','Local mock only: no files leave this computer and no OCR is performed. The example circuit is synthetic; unknown-safe keeps unrecognized schematic contents unresolved.','ai-mock-note'));
    const buttons=element('div',null,'action-row');inputPanel.append(buttons);
    action(buttons,'Save analysis inputs',guard(async()=>{await save();if(here())editor();}));
    action(buttons,'Analyze schematic + requirements',guard(async()=>{if(!inputs.documents.length)throw Error('Upload at least one schematic document.');await save();const result=await post(`/api/ai-design/tasks/${active.id}/analyze`,{expected_revision:active.revision,provider});active=result.task;run=result.run;source=null;if(here())editor();}));
    if(active){const link=element('a','Export analysis JSON','download');link.href=`/api/ai-design/tasks/${active.id}/export${run?'?run_id='+run.id:''}`;buttons.append(link);}
    if(active?.runs.length){field(inputPanel,'Analysis history',run?.id||'',async id=>{try{run=await api(`/api/ai-design/tasks/${active.id}/runs/${id}`);source=null;if(here())editor();}catch(e){$('workflow-error').textContent=e.message;}},Object.fromEntries(active.runs.map(r=>[r.id,`${r.created_at.slice(0,19)} · ${r.provider.model} · ${r.status}`])));}
    const layout=element('div',null,'ai-results-layout'),results=element('section');results.id='ai-results';const sourcePane=element('aside');sourcePane.id='ai-source';layout.append(results,sourcePane);content.append(layout);
    if(!run)results.append(element('p','Save inputs and run a local mock to review the circuit, proposed requirements and unresolved questions.'));
    else renderResult(results);
    renderSource();
  }
  function renderSource(){
    const pane=$('ai-source');if(!pane)return;pane.replaceChildren(element('h3','Source evidence'));
    if(!source){pane.append(element('p','Select Source on a claim to inspect its document location or exact original instruction.'));return;}
    if(source.evidence?.requirement_span){const original=run.inputs.engineering_requirements,quote=element('textarea');quote.readOnly=true;quote.rows=7;quote.value=original;quote.setAttribute('aria-label','Original instruction evidence');pane.append(quote,element('p','Quoted instruction: '+source.evidence.quote));quote.focus();quote.setSelectionRange(...source.evidence.requirement_span);return;}
    const document=source.document;
    if(!document){pane.append(element('p',source.evidence?.explanation||'No document location was asserted.'));return;}
    const asset=document.asset,page=source.evidence?.page||1,link=element('a','Open original · '+asset.name);link.href='/api/assets/'+asset.sha256+'#page='+page;link.target='_blank';link.rel='noopener';pane.append(link,element('p','SHA-256 '+asset.sha256,'ai-hash'));
    if(asset.media_type.startsWith('image/')){const wrapper=element('div',null,'ai-source-image'),img=element('img');img.src='/api/assets/'+asset.sha256;img.alt=asset.name;wrapper.append(img);if(source.evidence?.bbox){const [x,y,w,h]=source.evidence.bbox,box=element('span',null,'ai-source-box');box.style.cssText=`left:${100*x}%;top:${100*y}%;width:${100*w}%;height:${100*h}%`;box.setAttribute('aria-label','Referenced schematic region');wrapper.append(box);}pane.append(wrapper);}else pane.append(element('p',`PDF page ${page}. Open the original document to inspect this page. Page rendering and OCR are not performed by the mock.`));
    if(source.evidence)pane.append(element('p',source.evidence.quote||source.evidence.explanation));
  }
  function claimCard(claim,parent){
    const card=element('div',null,'ai-claim');card.dataset.claim=claim.id;parent.append(card);
    const review=active?.reviews?.[run.id]?.[claim.id],value=review?.status==='corrected'?review.corrected_value:claim.value,unit=review?.status==='corrected'?review.corrected_unit:claim.unit;
    card.append(element('strong',claim.predicate.replaceAll('_',' ')+' · '+(value??'Unknown')+(unit?' '+unit:'')),element('p',`${claim.kind} · ${claim.status} · confidence ${claim.confidence??'not reported'}`,'property-note'));
    if(review)card.append(element('p',`Engineer ${review.status}: ${review.decision}`),element('p','Original result: '+(claim.value??'Unknown')+' '+claim.unit,'property-note'));
    if(claim.explanation)card.append(element('p',claim.explanation,'property-note'));
    for(const id of claim.evidence_ids){const evidence=run.result.evidence.find(e=>e.id===id);action(card,'Source · '+claim.predicate,()=>{source={evidence,document:run.inputs.documents.find(d=>d.id===evidence.document_id)};renderSource();});}
    action(card,'Review '+claim.predicate,()=>{
      const form=element('div',null,'ai-review-form');let status=review?.status||'confirmed',text=String(value??''),newUnit=unit||'',decision=review?.decision||'';
      field(form,'Review status · '+claim.id,status,v=>status=v,{confirmed:'Confirmed by engineer',corrected:'Corrected by engineer',rejected:'Rejected by engineer'});
      field(form,'Corrected value · '+claim.id,text,v=>text=v);field(form,'Corrected unit · '+claim.id,newUnit,v=>newUnit=v);field(form,'Review decision · '+claim.id,decision,v=>decision=v);
      action(form,'Save review · '+claim.id,guard(async()=>{let corrected=text===''?null:typeof claim.value==='number'?Number(text):typeof claim.value==='boolean'?text==='true':text;if(typeof corrected==='number'&&!Number.isFinite(corrected))throw Error('Enter a finite corrected number.');active=await post(`/api/ai-design/tasks/${active.id}/runs/${run.id}/review`,{expected_revision:active.revision,decisions:[{claim_id:claim.id,status,corrected_value:corrected,corrected_unit:newUnit,decision}]});if(here())editor();}));card.append(form);
    });
  }
  function renderResult(parent){
    parent.append(element('h3','Hydraulic understanding'));
    parent.append(element('p',`${run.provider.is_mock?'MOCK · ':''}${run.provider.id} / ${run.provider.model} · ${run.latency_ms} ms · ${run.status}`));
    const stale=dirty||JSON.stringify(run.inputs)!==JSON.stringify(inputs);if(stale)parent.append(element('p','These results belong to an earlier input snapshot. Save and analyze again to use changed documents or requirements.','ai-stale'));
    if(run.status!=='completed'){parent.append(element('p','Analysis failed: '+run.error+'. Inputs and earlier successful results are retained.'));return;}
    const result=run.result,claims=Object.fromEntries(result.claims.map(c=>[c.id,c]));
    for(const warning of result.warnings)parent.append(element('p',warning,'ai-mock-note'));
    parent.append(element('p',`${result.components.length} components · ${result.ports.length} ports · ${result.nets.length} nets · ${result.design_intent.length} proposed requirements · ${result.unresolved.length} unresolved`,'ai-summary'));
    for(const [title,rows]of [['Components',result.components],['Hydraulic ports',result.ports],['Hydraulic nets',result.nets]]){
      const section=element('details');section.open=title==='Components';section.append(element('summary',title+' · '+rows.length));parent.append(section);
      for(const entity of rows){const card=element('section',null,'library-card');section.append(card);const label=entity.claim_ids.map(id=>claims[id]).find(c=>c.predicate==='label')?.value;card.append(element('h4',label||entity.id));if(entity.members)card.append(element('p',entity.members.join(' ↔ ')));if('component_id'in entity)card.append(element('p',entity.component_id?'Component: '+entity.component_id:'External manifold terminal'));for(const id of entity.claim_ids)claimCard(claims[id],card);}
    }
    const intent=element('section');intent.append(element('h3','Proposed design intent'));parent.append(intent);
    for(const item of result.design_intent){const card=element('section',null,'library-card');card.append(element('h4',`${item.target_labels.join(', ')||'Manifold'} · ${item.property.replaceAll('_',' ')}`),element('p',`${item.strength} · ${item.operator} · ${item.bound_entity_ids.length?'Explicit entity binding':'Target labels not yet bound to geometry'}`));claimCard(claims[item.claim_id],card);intent.append(card);}
    const unresolved=element('section');unresolved.append(element('h3','Unresolved & knowledge resolution'));parent.append(unresolved);
    for(const lookup of result.knowledge)unresolved.append(element('p',`${lookup.manufacturer} ${lookup.model||'Model unknown'} · ${lookup.status} · ${lookup.message}`));
    for(const item of result.unresolved){const card=element('div',null,'library-card');card.append(element('strong',item.reason.replaceAll('_',' ')),element('p',item.description));if(item.question)card.append(element('p',item.question));unresolved.append(card);}
    const raw=element('details');raw.append(element('summary','Inspect hydraulic representation JSON'));const pre=element('pre',JSON.stringify(result,null,2));pre.className='native-inspection';raw.append(pre);parent.append(raw);
  }
  $('ai-design-open').onclick=()=>{if(inputs&&dirty){open('AI Design · Hydraulic understanding');editor();}else library().catch(e=>$('workflow-error').textContent=e.message);};
  return {open:()=>$('ai-design-open').click()};
}
