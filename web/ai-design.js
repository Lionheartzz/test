import {engineeringName,engineeringText} from './engineering-labels.js';
import {aiGeneration} from './ai-generation.js';
import {runDiagnostics} from './ai-diagnostics.js';
import {uuidToken} from './crypto-utils.js';
import {analysisStatus,documentSummary} from './ai-management.js';

export function aiDesign(ctx,open){
  const {$,element,field,action,api,post,get,state}=ctx,content=$('workflow-content');
  let active=null,inputs=null,run=null,dirty=false,pending=false,provider='configured',providers=[],activeJob=null,jobTimer=null,screen=0,editorKey=null;
  const unsaved=new Map(),generationStates=new Map();let returnToEditor=true;
  let managementNavigation=null,managementView=null,returningToManagement=false;
  const editing=()=>here()&&$('workflow-title').textContent==='AI Design · Hydraulic intent';
  const stash=()=>{if(inputs&&(!active||dirty)){editorKey??=active?.id||uuidToken();unsaved.set(editorKey,{active:structuredClone(active),inputs:structuredClone(inputs),run:structuredClone(run),dirty});}};
  const fresh=()=>({title:'New hydraulic analysis',documents:(get()?.schematic_intent?.assets||[]).map(asset=>({id:'DOC_'+asset.sha256.slice(0,24),asset,page_count:asset.media_type.startsWith('image/')?1:null})),engineering_requirements:'',project_context:get()?.project_context||'metric',linked_project_id:state()?.project_id||null,project_engineering:get()?JSON.parse(JSON.stringify(get())):null});
  const here=()=>$('workflow-dialog').open&&$('workflow-title').textContent.startsWith('AI Design');
  const managing=()=>managementView?.isCurrent()&&!$('workflow-dialog').open;
  const guard=(fn,surface=null)=>async()=>{if(pending)return;pending=true;const target=surface?.host||content,error=surface?.error||$('workflow-error');target.querySelectorAll('button,input,select,textarea').forEach(x=>x.disabled=true);error.textContent='';try{await fn();}catch(e){if(!surface||surface.isCurrent())error.textContent=e.message;}finally{pending=false;if(surface?surface.isCurrent():here())target.querySelectorAll('button,input,select,textarea').forEach(x=>x.disabled=x.getAttribute('data-ai-running')==='true');}};
  const touched=()=>{dirty=true;if(managing())stash();const status=content.querySelector('.ai-save-state');if(status)status.textContent='Inputs changed · save before analysis';};
  const generator=aiGeneration(ctx,{open,back:()=>returnToEditor&&inputs?editor():library().catch(e=>$('workflow-error').textContent=e.message),session:()=>({task:active,run,dirty}),
    onPreflight:(task,plan)=>generationStates.set(task.id,{run:task.latest_run?.id,decisions:plan.blocked.length}),
    refreshTask:async id=>{const next=await api('/api/ai-design/tasks/'+id);if(active?.id===id)active=next;return next;},watchJob});
  async function watchJob(job,progress){let status=job;while(['queued','running'].includes(status.status)){if(progress?.isConnected)progress.textContent=status.message;await new Promise(resolve=>setTimeout(resolve,1000));status=await api('/api/ai-design/jobs/'+job.id);}if(managing())await library();if(status.status!=='completed')throw Error(status.message);return status.result;}
  function followAnalysisJob(job){activeJob=job;clearTimeout(jobTimer);const poll=async()=>{try{
    activeJob=await api('/api/ai-design/jobs/'+job.id);
    if(['queued','running'].includes(activeJob.status)){const status=editing()&&active?.id===job.task_id&&content.querySelector('.ai-job-state');if(status)status.textContent=activeJob.message+' You may close this dialog and return later.';jobTimer=setTimeout(poll,1000);return;}
    if(activeJob.status==='completed'&&active?.id===job.task_id&&!dirty){active=activeJob.result.task;inputs=structuredClone(active.inputs);run=activeJob.result.run;}
    if(editing()&&active?.id===job.task_id)editor();else if(managing())await library();
  }catch(e){activeJob={...job,status:'failed',message:e.message};if(editing()&&active?.id===job.task_id)editor();}};jobTimer=setTimeout(poll,250);}
  async function save(){const signature=JSON.stringify(inputs),result=await post('/api/ai-design/tasks',{inputs,task_id:active?.id||null,expected_revision:active?.revision||null});active=result;if(JSON.stringify(inputs)===signature){inputs=structuredClone(result.inputs);dirty=false;unsaved.delete(editorKey);editorKey=active.id;}if(managing())await library();return result;}
  async function upload(file){if(!['application/pdf','image/png','image/jpeg'].includes(file.type))throw Error('Use PDF, PNG or JPEG schematic files.');if(file.size>20_000_000)throw Error('Each document must be at most 20 MB.');const asset=await api('/api/assets',{method:'POST',headers:{'Content-Type':file.type,'X-File-Name':encodeURIComponent(file.name),'X-PMC-Request':'local-console'},body:file});if(!inputs.documents.some(d=>d.asset.sha256===asset.sha256))inputs.documents.push({id:'DOC_'+uuidToken().replaceAll('-',''),asset,page_count:asset.media_type.startsWith('image/')?1:null});touched();}

  async function settings(){returnToEditor=editing();await generator.settings(async()=>{providers=await api('/api/ai-design/providers');provider='configured';});}
  async function openAnalysis(id,surface=null){
    stash();const token=++screen,next=await api('/api/ai-design/tasks/'+id);let nextRun=null,error='';
    const attempt=next.latest_attempt||next.latest_run;
    if(attempt)try{nextRun=await api(`/api/ai-design/tasks/${id}/runs/${attempt.id}`);}catch(e){error=e.message;}
    if(token!==screen||!(surface?surface.isCurrent():here()))return;
    active=next;inputs=structuredClone(next.inputs);run=nextRun;dirty=false;editorKey=id;editor();if(error)$('workflow-error').textContent=error;
  }
  async function library(){
    stash();if(!managementNavigation)throw Error('Home AI Design Management is unavailable.');returningToManagement=true;try{return await managementNavigation();}finally{returningToManagement=false;}
  }
  async function mountManagement(host,{isCurrent}){
    stash();const token=++screen;host.replaceChildren();host.classList.add('ai-content');
    const content=element('div'),error=element('p',null,'error');error.setAttribute('role','alert');host.append(content,error);
    const surface={host:content,error,isCurrent};managementView={host,isCurrent};
    const guarded=fn=>guard(fn,surface);
    content.append(element('p','Manage schematic analyses and AI-generated manifold drafts.'));
    action(content,'New AI Design',guarded(async()=>{stash();active=null;inputs=fresh();run=null;dirty=false;editorKey=uuidToken();editor();}));
    action(content,'Provider Settings',guarded(settings));
    for(const [key,draft]of unsaved){const card=element('section',null,'library-card');content.append(card);card.append(element('h3','Unsaved AI Design'),element('p',draft.inputs.title+' · Inputs changed'));
      action(card,'Resume',guarded(async()=>{stash();const latest=unsaved.get(key);if(!latest){await mountManagement(host,{isCurrent});return;}({active,inputs,run,dirty}=structuredClone(latest));editorKey=key;editor();}));}
    let rows,available,current;
    try{[rows,available,current]=await Promise.all([api('/api/ai-design/tasks'),api('/api/ai-design/providers'),api('/api/ai-design/jobs/current')]);}
    catch(e){if(token===screen&&isCurrent()){error.textContent=e.message;action(content,'Retry loading AI Designs',()=>mountManagement(host,{isCurrent}));}return;}
    if(token!==screen||!isCurrent())return;
    providers=available;
    if(current?.operation==='analyze'&&['queued','running'].includes(current.status)&&activeJob?.id!==current.id)followAnalysisJob(current);
    const running=current&&['queued','running'].includes(current.status)?current:null;
    for(const row of rows){const card=element('section',null,'library-card');content.append(card);
      card.append(element('h3',row.title),element('p',documentSummary(row)),element('p','Analysis: '+analysisStatus(row,running)),
        element('p','Generated drafts: '+(row.generated_draft_count||0)),element('p','Updated: '+new Date(row.updated_at).toLocaleString()));
      if(running?.task_id===row.id&&running.operation==='generate')card.append(element('p','Draft generation: Running'));
      const generation=generationStates.get(row.id);if(generation&&!row.stale&&generation.run===row.latest_run?.id)card.append(element('p',generation.decisions?'Draft generation: Needs '+generation.decisions+' engineering decision'+(generation.decisions===1?'':'s'):'Draft generation: Ready to generate'));
      action(card,'Open',guarded(()=>openAnalysis(row.id,surface)));
      const remove=action(card,'Delete',guarded(async()=>{
        if(!confirm('Delete this AI Design workspace?\n\nIts analysis history and AI-generated draft outputs will be removed.\nSaved Manifold Projects are not affected.'))return;
        await api('/api/ai-design/tasks/'+row.id,{method:'DELETE',headers:{'X-PMC-Request':'local-console','Content-Type':'application/json'}});
        for(const [key,draft]of unsaved)if(draft.active?.id===row.id)unsaved.delete(key);
        if(active?.id===row.id){active=null;inputs=null;run=null;dirty=false;editorKey=null;}generationStates.delete(row.id);if(isCurrent())await mountManagement(host,{isCurrent});
      }));remove.disabled=running?.task_id===row.id;remove.setAttribute('data-ai-running',String(remove.disabled));
    }
    if(!rows.length&&!unsaved.size)content.append(element('p','No AI Designs yet. Start with a schematic and engineering requirements.'));
  }

  function resultView(parent){
    if(!run){parent.append(element('p','Save inputs and analyze the schematic to create hydraulic connections.'));return;}
    runDiagnostics(parent,run,{element});if(run.status!=='completed')return;
    const result=run.result;parent.append(element('h3','Hydraulic connections'),element('p',`${result.components.length} components · ${result.ports.length} ports · ${result.nets.length} nets · ${result.design_intent.length} requirements · ${result.unresolved.length} unresolved`,'ai-summary'));
    for(const [title,rows]of [['Components',result.components],['Hydraulic ports',result.ports],['Hydraulic nets',result.nets]]){const section=element('details');section.open=title==='Components';section.append(element('summary',title+' · '+rows.length));for(const row of rows){const card=element('section',null,'library-card');card.append(element('h4',engineeringName(row.label,'Item')));if(row.members)card.append(element('p',row.members.map(id=>{const p=result.ports.find(port=>port.id===id),c=result.components.find(component=>component.id===p?.component_id);return [engineeringName(c?.label,''),engineeringName(p?.label,'Port')].filter(Boolean).join(' · ');}).join(' ↔ ')));if(row.facts&&Object.keys(row.facts).length)Object.entries(row.facts).filter(([,value])=>value!==null&&['string','number','boolean'].includes(typeof value)).forEach(([name,value])=>card.append(element('p',observationName(row,name)+': '+engineeringText(value))));unconfirmedReadings(card,row);section.append(card);}parent.append(section);}
    if(result.design_intent.length){const section=element('details');section.append(element('summary','Design intent · '+result.design_intent.length));for(const row of result.design_intent)section.append(element('p',`${row.target_labels.join(', ')||'Manifold'} · ${row.property} ${row.operator} ${row.value??'unresolved'} ${row.unit||''}`));parent.append(section);}
    for(const row of result.unresolved)parent.append(element('p',engineeringText(row.description),'ai-provider-note'));
    if(run.identity_reading?.captions?.length){
      const captions=element('details');captions.append(element('summary','Original identity annotations · '+run.identity_reading.captions.length));
      for(const [index,row] of run.identity_reading.captions.entries())captions.append(element('p',`${index+1} · Document ${row.document}, page ${row.page}: ${row.quote}`));
      parent.append(captions);
    }
  }

  function observationName(row,name){
    return name==='model'&&run?.identity_interpretations?.[row.id]?.model_role==='engineering_interface'
      ?'machining interface':name.replaceAll('_',' ');
  }

  function unconfirmedReadings(parent,row){
    for(const text of row.observed_identity_annotations||[])parent.append(element('p','Observed annotation: '+engineeringText(text),'property-note'));
    if(row.members&&row.status&&row.status!=='confirmed')parent.append(element('p','AI connection proposal · unconfirmed. Review the schematic before relying on this connection.','review-warning'));
    const readings=Object.entries(row.unconfirmed_observations||{}).filter(([,reading])=>reading.value!=null&&['string','number','boolean'].includes(typeof reading.value));
    if(!readings.length)return;
    parent.append(element('p','AI readings · unconfirmed. These are proposals, not defined engineering facts.','review-warning'));
    for(const [name,reading]of readings)parent.append(element('p',engineeringText(name.replaceAll('_',' '))+': '+engineeringText(reading.value)+(reading.unit?' '+engineeringText(reading.unit):'')));
  }

  function editor(){
    ++screen;open('AI Design · Hydraulic intent');content.classList.add('ai-content');const nav=element('div',null,'action-row');content.append(nav);action(nav,'Back to AI Design Management',()=>library().catch(e=>$('workflow-error').textContent=e.message));action(nav,'Provider settings',()=>settings().catch(e=>$('workflow-error').textContent=e.message));nav.append(element('span',dirty?'Inputs changed · save before analysis':active?'Saved locally':'New analysis · not saved','ai-save-state'));
    const panel=element('section',null,'ai-inputs');content.append(panel);field(panel,'Analysis title',inputs.title,v=>{inputs.title=v;touched();});field(panel,'Engineering unit context',inputs.project_context,v=>{inputs.project_context=v;touched();},{metric:'Metric',inch:'Inch'});
    const file=element('input');file.type='file';file.multiple=true;file.accept='.pdf,.png,.jpg,.jpeg';file.setAttribute('aria-label','Upload schematic documents');panel.append(file);file.onchange=guard(async()=>{for(const item of file.files)await upload(item);if(editing())editor();else if(managing())await library();});
    for(const document of inputs.documents){const row=element('div',null,'action-row');row.append(element('span',document.asset.name));const link=element('a','Open document');link.href='/api/assets/'+document.asset.sha256;link.target='_blank';link.rel='noopener';row.append(link);action(row,'Remove',()=>{inputs.documents=inputs.documents.filter(d=>d.id!==document.id);touched();if(editing())editor();});panel.append(row);}
    const label=element('label','Engineering requirements','field'),requirements=element('textarea');requirements.rows=7;requirements.value=inputs.engineering_requirements;requirements.oninput=()=>{inputs.engineering_requirements=requirements.value;touched();};label.append(requirements);panel.append(label);
    field(panel,'Analysis provider',provider,v=>provider=v,Object.fromEntries(providers.map(p=>[p.id,`${p.provider} / ${p.model}`])));
    panel.append(element('p','Analysis uses two AI stages: read the original identity annotations, then interpret the schematic with matches from the local Engineering Library. Both stages share the configured timeout.','property-note'));
    const buttons=element('div',null,'action-row');panel.append(buttons);action(buttons,'Save inputs',guard(async()=>{await save();if(editing())editor();}));const running=activeJob&&active&&activeJob.task_id===active.id&&['queued','running'].includes(activeJob.status);if(!running)action(buttons,'Start analysis',guard(async()=>{if(!inputs.documents.length)throw Error('Upload at least one schematic document.');await save();const job=await post(`/api/ai-design/tasks/${active.id}/analyze-job`,{expected_revision:active.revision,provider});followAnalysisJob(job);if(editing())editor();else if(managing())await library();}));if(running)panel.append(element('p',activeJob.message+' You may close this dialog and return later.','ai-job-state'));else if(activeJob&&active&&activeJob.task_id===active.id&&activeJob.status!=='completed')panel.append(element('p',activeJob.message,'error'));if(run?.status==='completed'){action(buttons,'Create manifold draft',guard(()=>{returnToEditor=true;return generator.prepare();})).classList.add('primary');const exportLink=element('a','Download analysis');exportLink.href=`/api/ai-design/tasks/${active.id}/export?`+new URLSearchParams({run_id:run.id});exportLink.className='download';buttons.append(exportLink);}
    const results=element('section');results.id='ai-results';content.append(results);resultView(results);
    if(active?.generations?.length){const previous=element('section',null,'library-card');previous.append(element('h3','Previous generated manifold drafts'));for(const item of [...active.generations].reverse()){const row=element('div',null,'action-row');row.append(element('span',`${item.created_at} · ${item.status}`));action(row,'Open generated draft',guard(async()=>generator.showPacket(await api(`/api/ai-design/tasks/${active.id}/generations/${item.id}`))));previous.append(row);}content.append(previous);}
  }
  $('ai-design-open').onclick=()=>library().catch(e=>$('workflow-error').textContent=e.message);
  $('workflow-dialog').addEventListener('close',()=>{if(!returningToManagement&&managing()&&$('workflow-title').textContent.startsWith('AI Design'))mountManagement(managementView.host,{isCurrent:managementView.isCurrent});});
  return {open:()=>$('ai-design-open').click(),mountManagement,setManagementNavigation:callback=>managementNavigation=callback};
}
