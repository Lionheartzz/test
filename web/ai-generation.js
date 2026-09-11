// Local settings and engineering handoff reuse the normal Studio draft workflow.
export function aiGeneration(ctx, {open, back, session, refreshTask, watchJob}) {
  const {$,element,field,action,api,post,newProject}=ctx, content=$('workflow-content');
  const faceOptions={'':'Use interpreted requirements / proposal',top:'Top',bottom:'Bottom',left:'Left',right:'Right',front:'Front',back:'Back'};
  let options={},optionRun=null,screen=0,busy=false;
  const here=()=>$('workflow-dialog').open&&$('workflow-title').textContent.startsWith('AI Design');
  const safe=fn=>async()=>{try{await fn();}catch(e){$('workflow-error').textContent=e.message;}};
  function reset(run){if(optionRun!==run.id){optionRun=run.id;options={bindings:{},port_definitions:{},net_overrides:{},component_faces:{},port_faces:{},topology_decision:'',placement_decision:'',drilling_diameter:8,port_diameter:12,port_depth:12,minimum_wall:7,max_attempts:4};}}
  function check(parent,label,value,onChange){const wrap=element('label',null,'ai-check'),input=element('input');input.type='checkbox';input.checked=value;input.setAttribute('aria-label',label);input.onchange=()=>onChange(input.checked);wrap.append(input,document.createTextNode(label));parent.append(wrap);return input;}

  async function settings(onSaved){
    const token=++screen;open('AI Design · Provider settings');content.classList.add('ai-content');
    content.append(element('p','Configure your own multimodal endpoint and model. Credentials stay in this computer’s private local settings file and are never exported with a project.'));
    const current=await api('/api/ai-design/settings');if(token!==screen||!here())return;
    if(current.configuration_warning)content.append(element('p',current.configuration_warning,'review-warning'));
    const form=element('section',null,'ai-inputs');content.append(form);
    const value=Object.fromEntries(Object.entries(current).filter(([key])=>!['ready','key_present','configuration_warning'].includes(key)));value.api_key='';
    field(form,'Provider label',value.label,v=>value.label=v);
    field(form,'API base URL',value.base_url,v=>value.base_url=v).placeholder='Your API base URL, without /chat/completions';
    field(form,'Model identifier',value.model,v=>value.model=v).placeholder='Your multimodal model ID';
    field(form,'Transport',value.transport,v=>value.transport=v,{'chat-completions':'Chat Completions · multimodal image input'});
    const key=field(form,'API key',null,v=>value.api_key=v);key.type='password';key.autocomplete='new-password';key.placeholder=current.key_present?'Stored key · leave blank to keep it for the same endpoint':'Enter locally; never paste a key into analysis requirements';
    check(form,'Enable this provider',value.enabled,v=>value.enabled=v);
    check(form,'Endpoint explicitly allows anonymous access',value.anonymous,v=>value.anonymous=v);
    check(form,'Request JSON object output',value.json_mode,v=>value.json_mode=v);
    for(const [name,label]of [['max_tokens','Maximum output tokens'],['timeout_seconds','Total provider timeout (seconds)'],['max_pages','Maximum pages per analysis'],['image_max_side','Maximum image side (pixels)']])field(form,label,value[name],v=>value[name]=v,null,true);
    form.append(element('p','The selected provider must support image_url data images. PDFs are rendered locally into pages. Files and original requirements are sent only when you start an analysis. Changing the endpoint requires entering its key again.','property-note'));
    action(form,'Save provider settings',safe(async()=>{const result=await post('/api/ai-design/settings',value);key.value='';value.api_key='';await onSaved(result);if(here())back();}));
    if(current.key_present)action(form,'Forget stored API key',safe(async()=>{await post('/api/ai-design/settings/clear-key',{});await onSaved({ready:false});if(here())back();}));
    action(form,'Back to analysis',back);
  }

  async function prepare(autoGenerate=false){
    const {task,run,dirty}=session();if(!task||!run||run.status!=='completed')throw Error('Complete an analysis first.');
    if(dirty)throw Error('Save and analyze your changed inputs first.');
    reset(run);const token=++screen;open('AI Design · Create manifold draft');content.classList.add('ai-content');
    content.append(element('p','Resolving existing library data and engineering requirements…','loading-state'));
    const plan=await post(`/api/ai-design/tasks/${task.id}/generation/preflight`,{expected_revision:task.revision,run_id:run.id,options});
    if(token!==screen||!here())return;
    renderPlan(task,run,plan);
    if(autoGenerate&&plan.ready)await generate(task,run);
  }

  function renderPlan(task,run,plan){
    open('AI Design · Create manifold draft');content.classList.add('ai-content');
    action(content,'Back to hydraulic analysis',back);
    content.append(element('p',`${run.provider.is_mock?'MOCK analysis':'AI analysis'} · ${run.provider.id} / ${run.provider.model}. The result will open as an editable Draft, with exact checks and unresolved engineering decisions visible.`,'ai-mock-note'));
    if(plan.blocked.length){const list=element('ul',null,'ai-blocked');for(const message of plan.blocked)list.append(element('li',message));content.append(list);}
    content.append(element('h3','Cartridges and hydraulic windows'));
    if(!plan.components.length)content.append(element('p','No cartridges in this circuit. A port/distribution block can be generated if the net topology is usable.'));
    for(const component of plan.components){
      const card=element('section',null,'library-card');content.append(card);card.append(element('h4',component.label+(component.model?' · '+component.model:'')));
      const binding=options.bindings[component.id],definition=component.definition;
      if(definition){
        card.append(element('p',`${definition.label} · ${definition.unit} · ${definition.geometry_status}`));
        if(component.automatic)card.append(element('p','Source-backed candidate and matching numbered windows found. Draft generation keeps the component unconfirmed for engineer review.'));
        const ports=Object.fromEntries(plan.ports.filter(p=>p.component_id===component.id).map(p=>[p.id,`${p.label} → ${p.net||'Unknown net'}`]));
        for(const zone of definition.zones){
          const label=`${component.label} · window ${zone.id} → schematic port`;
          if(binding)field(card,label,binding.zone_ports[zone.id]||'',v=>{binding.zone_ports[zone.id]=v;},{'':'Choose a port',...ports});
          else card.append(element('p',label+': '+(ports[component.mapping[zone.id]]||component.mapping[zone.id]||'Unmapped')));
        }
        if(binding)field(card,`Cavity / mapping decision · ${component.label}`,binding.decision,v=>binding.decision=v).placeholder='Confirm why this cavity and port mapping are appropriate for this draft';
      }else card.append(element('p','No reliable automatic cavity mapping. Choose an existing source or PMC definition; the model cannot invent machining dimensions.'));
      for(const choice of component.choices)action(card,'Use candidate '+choice.label,safe(()=>selectCavity(component,choice,plan)));
      librarySearch(card,task,'cartridge-cavity',component.label,choice=>selectCavity(component,choice,plan));
      field(card,'Mounting face · '+component.label,options.component_faces[component.id]||'',v=>{if(v)options.component_faces[component.id]=v;else delete options.component_faces[component.id];},faceOptions);
    }
    content.append(element('h3','External ports'));
    for(const port of plan.external_ports){
      const card=element('section',null,'library-card');content.append(card);card.append(element('h4',port.label),element('p','Schematic specification: '+(port.specification||'Unknown')));
      if(port.definition){card.append(element('p','Selected: '+port.definition.label));field(card,'Port definition decision · '+port.label,options.port_definitions[port.id]?.decision||'',v=>options.port_definitions[port.id].decision=v);action(card,'Use provisional straight bore · '+port.label,()=>{delete options.port_definitions[port.id];prepare().catch(e=>$('workflow-error').textContent=e.message);});}
      else card.append(element('p','Provisional unthreaded straight bore. Its draft dimensions are shown below; thread and fitting compatibility stay unresolved.'));
      field(card,'Port face · '+port.label,options.port_faces[port.id]||'',v=>{if(v)options.port_faces[port.id]=v;else delete options.port_faces[port.id];},faceOptions);
      librarySearch(card,task,'external-port',port.label,async choice=>{options.port_definitions[port.id]={definition_key:choice.key,definition_sha256:choice.sha256,zone_ports:{},decision:''};await prepare();});
    }
    const topology=element('details');topology.open=plan.ports.some(p=>!p.net);topology.append(element('summary','Review / correct hydraulic net assignments'));content.append(topology);
    topology.append(element('p','Net IDs: '+plan.nets.map(n=>n.id+' = '+n.label).join(' · ')));
    for(const port of plan.ports)field(topology,'Net · '+(port.component_id?port.component_id+'.':'')+port.label,options.net_overrides[port.id]||port.net||'',v=>{if(v.trim())options.net_overrides[port.id]=v.trim();else delete options.net_overrides[port.id];});
    field(topology,'Topology correction decision',options.topology_decision,v=>options.topology_decision=v);
    field(content,'Placement override decision',options.placement_decision,v=>options.placement_decision=v).placeholder='Required only when overriding proposed component/port faces';
    const dimensions=element('details');dimensions.append(element('summary','Draft geometry assumptions and search budget'));content.append(dimensions);
    for(const [key,label]of [['drilling_diameter','Minimum proposed drilling diameter (mm)'],['port_diameter','Provisional port bore diameter (mm)'],['port_depth','Provisional port entry depth (mm)'],['minimum_wall','Minimum wall (mm)'],['max_attempts','Maximum layout attempts']])field(dimensions,label,options[key],v=>options[key]=v,null,true);
    dimensions.append(element('p','These are visible prototype geometry choices, not vendor specifications. Flow requirements may increase drilling size. Source cavity geometry is never resized.'));
    content.append(element('h3','How your requirements will be used'));
    for(const row of plan.dispositions){const card=element('div',null,'library-card');card.append(element('strong',`${row.property} · ${row.status.replaceAll('_',' ')}`),element('p',row.message));content.append(card);}
    const controls=element('div',null,'action-row');content.append(controls);
    action(controls,'Recheck choices and requirements',safe(()=>prepare()));
    action(controls,'Generate editable 3D draft',safe(()=>generate(task,run)));
    const progress=element('p','', 'ai-job-state');progress.setAttribute('role','status');content.append(progress);
  }

  async function selectCavity(component,choice,plan){
    const ports=plan.ports.filter(p=>p.component_id===component.id),mapping={};
    for(const zone of choice.zones){const normalized=zone.id.toLowerCase().replace(/^port/,'');const match=ports.find(p=>p.label.toLowerCase().replace(/^port/,'')===normalized);if(match)mapping[zone.id]=match.id;}
    options.bindings[component.id]={definition_key:choice.key,definition_sha256:choice.sha256,zone_ports:mapping,decision:''};await prepare();
  }

  function librarySearch(parent,task,role,label,onSelect){
    const details=element('details');details.append(element('summary','Search '+(role==='external-port'?'port machining definitions':'existing cavities')));parent.append(details);
    let query='';const input=field(details,'Library search · '+label,query,v=>query=v),results=element('div');details.append(results);
    action(details,'Search library · '+label,safe(async()=>{query=input.value;results.replaceChildren(element('p','Searching native '+task.inputs.project_context+' and saved PMC definitions…'));
      const rows=await api(`/api/ai-design/tasks/${task.id}/library-choices?`+new URLSearchParams({q:query,role}));if(!details.isConnected)return;results.replaceChildren();
      for(const row of rows){const card=element('div',null,'ai-choice');card.append(element('p',`${row.label} · ${row.manufacturer} · ${row.unit} · ${row.geometry_status}`));action(card,'Choose '+row.label,safe(()=>onSelect(row)));results.append(card);}
      if(!rows.length)results.append(element('p','No matches. Refine the native cavity designation or add an engineer-reviewed PMC definition through the existing Library.'));
    }));
  }

  async function generate(task,run){
    if(busy)return;busy=true;
    try{
      const payload={expected_revision:task.revision,run_id:run.id,options};
      const plan=await post(`/api/ai-design/tasks/${task.id}/generation/preflight`,payload);
      if(!plan.ready){renderPlan(task,run,plan);return;}
      content.querySelectorAll('button,input,select,textarea').forEach(e=>e.disabled=true);
      const progress=content.querySelector('.ai-job-state')||content.appendChild(element('p','', 'ai-job-state'));
      const job=await post(`/api/ai-design/tasks/${task.id}/generation/jobs`,payload);
      const result=await watchJob(job,progress);
      await refreshTask(task.id);
      if(here())showPacket(result);
    }finally{busy=false;if(here())content.querySelectorAll('button,input,select,textarea').forEach(e=>e.disabled=false);}
  }

  function showPacket(packet){
    open('AI Design · Generated manifold draft');content.classList.add('ai-content');
    content.append(element('h3',packet.status==='draft'?'Your editable manifold draft':'Generation needs review'),element('p',packet.message||packet.status));
    if(packet.status==='draft'){
      content.append(element('p',`Exact report: ${packet.validation.counts.PASS} PASS · ${packet.validation.counts.WARNING} WARNING · ${packet.validation.counts.FAIL} FAIL. Geometry failures: ${packet.geometry_failures}.`,'ai-summary'));
      content.append(element('p','The draft preserves all failed checks and open engineering decisions. Opening it does not mark it approved. Move, replace, reroute, save and validate in the normal Studio.','ai-mock-note'));
      action(content,'Open draft in Manifold Studio',()=>{if(newProject(packet.design)){$('workflow-dialog').close();ctx.notice('AI Draft opened. Review the linked analysis and engineering decisions, then Save Project or Save & Validate.');}}).classList.add('primary');
      const a=element('a','Download draft project JSON');a.href=`/api/ai-design/tasks/${packet.task_id}/generations/${packet.id}/project`;a.className='download';content.append(a);
      for(const attempt of packet.attempts){content.append(element('p',`Candidate ${attempt.index+1}: ${attempt.error||`${attempt.geometry_failures} geometry failures · ${attempt.counts.FAIL} total FAIL · ${(attempt.failed_rules||[]).join(', ')||'no failed rules'}`}`));}
      const failures=element('details');failures.append(element('summary','Inspect retained exact validation failures'));for(const check of packet.validation.checks.filter(c=>c.status==='FAIL'))failures.append(element('p',`${check.rule} · ${check.items.join(', ')} · ${check.message}`));content.append(failures);
    }
    for(const row of packet.dispositions||[]){const card=element('div',null,'library-card');card.append(element('strong',`${row.property} · ${row.status}`),element('p',row.message));content.append(card);}
    action(content,'Return to analysis',back);
  }
  return {settings,prepare,showPacket};
}
