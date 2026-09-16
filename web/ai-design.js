import {aiGeneration} from './ai-generation.js';
import {attemptStatus,runDiagnostics} from './ai-diagnostics.js';

export function aiDesign(ctx,open){
  const {$,element,field,action,api,post,get,state}=ctx,content=$('workflow-content');
  let active=null,inputs=null,run=null,dirty=false,pending=false,provider='configured',providers=[];
  const fresh=()=>({title:'New hydraulic analysis',documents:[],engineering_requirements:'',project_context:get()?.project_context||'metric',linked_project_id:state()?.project_id||null});
  const here=()=>$('workflow-dialog').open&&$('workflow-title').textContent.startsWith('AI Design');
  const guard=fn=>async()=>{if(pending)return;pending=true;content.querySelectorAll('button,input,select,textarea').forEach(x=>x.disabled=true);$('workflow-error').textContent='';try{await fn();}catch(e){$('workflow-error').textContent=e.message;}finally{pending=false;if(here())content.querySelectorAll('button,input,select,textarea').forEach(x=>x.disabled=false);}};
  const touched=()=>{dirty=true;const status=content.querySelector('.ai-save-state');if(status)status.textContent='Inputs changed · save before analysis';};
  const generator=aiGeneration(ctx,{open,back:()=>inputs?editor():library(),session:()=>({task:active,run,dirty}),
    refreshTask:async id=>{const next=await api('/api/ai-design/tasks/'+id);if(active?.id===id)active=next;return next;},watchJob});
  async function watchJob(job,progress){let status=job;while(['queued','running'].includes(status.status)){if(progress?.isConnected)progress.textContent=status.message;await new Promise(resolve=>setTimeout(resolve,1000));status=await api('/api/ai-design/jobs/'+job.id);}if(status.status!=='completed')throw Error(status.message);return status.result;}
  async function save(){const signature=JSON.stringify(inputs),result=await post('/api/ai-design/tasks',{inputs,task_id:active?.id||null,expected_revision:active?.revision||null});active=result;if(JSON.stringify(inputs)===signature){inputs=structuredClone(result.inputs);dirty=false;}return result;}
  async function upload(file){if(!['application/pdf','image/png','image/jpeg'].includes(file.type))throw Error('Use PDF, PNG or JPEG schematic files.');if(file.size>20_000_000)throw Error('Each document must be at most 20 MB.');const asset=await api('/api/assets',{method:'POST',headers:{'Content-Type':file.type,'X-File-Name':encodeURIComponent(file.name),'X-PMC-Request':'local-console'},body:file});if(!inputs.documents.some(d=>d.asset.sha256===asset.sha256))inputs.documents.push({id:'DOC_'+crypto.randomUUID().replaceAll('-',''),asset,page_count:asset.media_type.startsWith('image/')?1:null});touched();}

  async function settings(){await generator.settings(async()=>{providers=await api('/api/ai-design/providers');provider='configured';});}
  async function library(){
    open('AI Design · Analysis workspaces');content.classList.add('ai-content');
    content.append(element('p','Analyze explicit schematic intent, then generate a project using the same SQLite cavity and cartridge IDs as manual workflows.'));
    action(content,'Provider settings',()=>settings().catch(e=>$('workflow-error').textContent=e.message));
    const [rows,available]=await Promise.all([api('/api/ai-design/tasks'),api('/api/ai-design/providers')]);providers=available;
    action(content,'New analysis',()=>{active=null;inputs=fresh();run=null;dirty=false;editor();});
    for(const row of rows){const card=element('section',null,'library-card'),last=row.latest_attempt||row.latest_run;card.append(element('h3',row.title),element('p',`${row.documents} documents · ${attemptStatus(last)}${row.stale?' · inputs changed':''}`));action(card,'Open analysis',guard(async()=>{active=await api('/api/ai-design/tasks/'+row.id);inputs=structuredClone(active.inputs);dirty=false;const attempt=active.latest_attempt||active.latest_run;run=attempt?await api(`/api/ai-design/tasks/${row.id}/runs/${attempt.id}`):null;editor();}));content.append(card);}
    if(!rows.length)content.append(element('p','No analyses yet. Start with a schematic and engineering requirements.'));
  }

  function resultView(parent){
    if(!run){parent.append(element('p','Save inputs and analyze the schematic to create normalized hydraulic intent.'));return;}
    runDiagnostics(parent,run,{element});if(run.status!=='completed'){parent.append(element('p','Analysis failed: '+run.error));return;}
    const result=run.result;parent.append(element('h3','Normalized hydraulic intent'),element('p',`${result.components.length} components · ${result.ports.length} ports · ${result.nets.length} nets · ${result.design_intent.length} requirements · ${result.unresolved.length} unresolved`,'ai-summary'));
    for(const [title,rows]of [['Components',result.components],['Hydraulic ports',result.ports],['Hydraulic nets',result.nets]]){const section=element('details');section.open=title==='Components';section.append(element('summary',title+' · '+rows.length));for(const row of rows){const card=element('section',null,'library-card');card.append(element('h4',row.label||row.id));if(row.members)card.append(element('p',row.members.join(' ↔ ')));if(row.facts&&Object.keys(row.facts).length)card.append(element('pre',JSON.stringify(row.facts,null,2)));section.append(card);}parent.append(section);}
    if(result.design_intent.length){const section=element('details');section.append(element('summary','Design intent · '+result.design_intent.length));for(const row of result.design_intent)section.append(element('p',`${row.target_labels.join(', ')||'Manifold'} · ${row.property} ${row.operator} ${row.value??'unresolved'} ${row.unit||''}`));parent.append(section);}
    for(const row of result.unresolved)parent.append(element('p',row.reason+': '+row.description,'ai-provider-note'));
  }

  function editor(){
    open('AI Design · Hydraulic intent');content.classList.add('ai-content');const nav=element('div',null,'action-row');content.append(nav);action(nav,'All analyses',library);action(nav,'Provider settings',()=>settings().catch(e=>$('workflow-error').textContent=e.message));nav.append(element('span',dirty?'Inputs changed · save before analysis':active?'Saved locally':'New analysis · not saved','ai-save-state'));
    const panel=element('section',null,'ai-inputs');content.append(panel);field(panel,'Analysis title',inputs.title,v=>{inputs.title=v;touched();});field(panel,'Engineering unit context',inputs.project_context,v=>{inputs.project_context=v;touched();},{metric:'Metric',inch:'Inch'});
    const file=element('input');file.type='file';file.multiple=true;file.accept='.pdf,.png,.jpg,.jpeg';file.setAttribute('aria-label','Upload schematic documents');panel.append(file);file.onchange=guard(async()=>{for(const item of file.files)await upload(item);editor();});
    for(const document of inputs.documents){const row=element('div',null,'action-row');row.append(element('span',document.asset.name));action(row,'Remove',()=>{inputs.documents=inputs.documents.filter(d=>d.id!==document.id);touched();editor();});panel.append(row);}
    const label=element('label','Engineering requirements','field'),requirements=element('textarea');requirements.rows=7;requirements.value=inputs.engineering_requirements;requirements.oninput=()=>{inputs.engineering_requirements=requirements.value;touched();};label.append(requirements);panel.append(label);
    field(panel,'Analysis provider',provider,v=>provider=v,Object.fromEntries(providers.map(p=>[p.id,`${p.provider} / ${p.model}`])));
    const buttons=element('div',null,'action-row');panel.append(buttons);action(buttons,'Save inputs',guard(async()=>{await save();editor();}));action(buttons,'Analyze',guard(async()=>{if(!inputs.documents.length)throw Error('Upload at least one schematic document.');await save();const response=await post(`/api/ai-design/tasks/${active.id}/analyze`,{expected_revision:active.revision,provider});active=response.task;run=response.run;editor();}));if(run?.status==='completed')action(buttons,'Create manifold draft',guard(()=>generator.prepare())).classList.add('primary');
    const results=element('section');results.id='ai-results';content.append(results);resultView(results);
  }
  $('ai-design-open').onclick=()=>{if(inputs&&dirty)editor();else library().catch(e=>$('workflow-error').textContent=e.message);};
  return {open:()=>$('ai-design-open').click()};
}
