// Local settings and engineering handoff reuse the normal Studio draft workflow.
export async function inspectGeneratedDraft(packet,post){
  const inspection=await post('/api/import-project',packet.design);
  return {design:inspection.design,definitions:inspection.engineering?.definitions||{},threads:inspection.engineering?.threads||{}};
}

export function aiGeneration(ctx, {open, back, session, refreshTask, watchJob}) {
  const {$,element,field,action,api,post,newProject}=ctx, content=$('workflow-content');
  const faceOptions={'':'Use interpreted requirements / proposal',top:'Top',bottom:'Bottom',left:'Left',right:'Right',front:'Front',back:'Back'};
  let options={},optionRun=null,screen=0,busy=false;
  const here=()=>$('workflow-dialog').open&&$('workflow-title').textContent.startsWith('AI Design');
  const safe=fn=>async()=>{try{await fn();}catch(e){$('workflow-error').textContent=e.message;}};
  function reset(run){if(optionRun!==run.id){optionRun=run.id;options={bindings:{},port_definitions:{},provisional_ports:{},threaded_mounting_holes:[],mounting_decision:'',net_overrides:{},component_faces:{},port_faces:{},topology_decision:'',placement_decision:'',drilling_diameter:8,port_diameter:12,port_depth:12,minimum_wall:7,max_attempts:4};}}
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
    const tokens=field(form,'Maximum output tokens',value.max_tokens==null?'':String(value.max_tokens),v=>value.max_tokens=v.trim()||null);tokens.inputMode='numeric';tokens.pattern='[0-9]*';tokens.placeholder='Blank = omit parameter; no PMC upper limit';
    field(form,'Output token parameter',value.max_tokens_parameter,v=>value.max_tokens_parameter=v,{max_tokens:'max_tokens',max_completion_tokens:'max_completion_tokens'});
    form.append(element('p','Any positive integer is passed unchanged. Blank uses the provider/model default. Provider context limits still apply; reasoning may share the output budget.','property-note'));
    const reasoning=element('section',null,'library-card');form.append(reasoning);reasoning.append(element('h3','Thinking / reasoning controls'));
    let scope='default';const reasonFields=element('div');
    const drawReasoning=()=>{reasonFields.replaceChildren();const inherited=scope!=='default'&&!value.operation_reasoning[scope];
      if(scope!=='default')check(reasonFields,'Override reasoning for this task',!inherited,enabled=>{if(enabled)value.operation_reasoning[scope]=structuredClone(value.reasoning);else delete value.operation_reasoning[scope];drawReasoning();});
      if(inherited){reasonFields.append(element('p','Uses the default reasoning controls.'));return;}
      const chosen=scope==='default'?value.reasoning:value.operation_reasoning[scope];
      field(reasonFields,'Reasoning parameter dialect',chosen.dialect,v=>chosen.dialect=v,{provider_default:'Provider default · send no controls',reasoning_effort:'reasoning_effort · compatible endpoints',thinking:'thinking.type + reasoning_effort · supporting endpoints'});
      field(reasonFields,'Thinking mode',chosen.mode,v=>chosen.mode=v,{provider_default:'Provider default',enabled:'Enabled',disabled:'Disabled'});
      field(reasonFields,'Reasoning effort',chosen.effort,v=>chosen.effort=v,Object.fromEntries(['provider_default','none','minimal','low','medium','high','xhigh','max','ultra'].map(v=>[v,v==='provider_default'?'Provider default':v])));
    };
    field(reasoning,'Reasoning task',scope,v=>{scope=v;drawReasoning();},{default:'Default for all tasks',hydraulic_understanding:'Schematic extraction (current)',topology_reasoning:'Topology reasoning (future task)',manifold_optimization:'Manifold optimization (future task)'});reasoning.append(reasonFields);drawReasoning();
    reasoning.append(element('p','Choose the dialect documented by your endpoint. Unsupported controls may be rejected or ignored by the provider. Requested controls and any PMC omissions appear in each run; PMC never infers support from a model name.','property-note'));
    field(form,'Automatic contract retries',String(value.contract_retries),v=>value.contract_retries=Number(v),{'0':'None · one request per analysis','1':'One retry after invalid semantic output · repeats page inputs'});
    check(form,'Stream provider response',value.stream,v=>value.stream=v);
    check(form,'Request streaming usage statistics',value.stream_usage,v=>value.stream_usage=v);
    form.append(element('p','Streaming must be supported by the endpoint. Usage may arrive only at the end; interrupted calls can still have unavailable totals. Auth, HTTP, timeout and truncation failures are never automatically retried.','property-note'));
    for(const [name,label]of [['timeout_seconds','Total provider timeout (seconds)'],['max_pages','Maximum pages per analysis'],['image_max_side','Maximum image side (pixels)']])field(form,label,value[name],v=>value[name]=v,null,true);
    form.append(element('p','The selected provider must support image_url data images. PDFs are rendered locally into pages. Files and original requirements are sent only when you start an analysis. Changing the endpoint requires entering its key again.','property-note'));
    action(form,'Save provider settings',safe(async()=>{const raw=tokens.value.trim();if(raw&&(!/^[0-9]+$/.test(raw)||BigInt(raw)<1n))throw Error('Maximum output tokens must be a positive whole number, or blank for the provider default.');value.max_tokens=raw||null;const result=await post('/api/ai-design/settings',value);key.value='';value.api_key='';await onSaved(result);if(here())back();}));
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

  function renderPlan(task,run,plan,attempted=false){
    open('AI Design · Create manifold draft');content.classList.add('ai-content');
    action(content,'Back to hydraulic analysis',back);
    content.append(element('p',`${run.provider.is_mock?'MOCK analysis':'AI analysis'} · ${run.provider.id} / ${run.provider.model}. The result will open as an editable Draft, with exact checks and unresolved engineering decisions visible.`,'ai-provider-note'));
    if(plan.blocked.length){const summary=element('section',null,'ai-blocked');summary.setAttribute('role','alert');summary.tabIndex=-1;
      summary.append(element('h3',attempted?`Draft not generated · ${plan.blocked.length} blockers remain`:`Draft generation needs ${plan.blocked.length} decisions`),element('p','Resolve the items below, then recheck or generate again. Your saved analysis is retained; no new AI call is needed.'));
      const list=element('ul');for(const message of plan.blocked)list.append(element('li',message));summary.append(list);content.append(summary);
      if(attempted){summary.focus();summary.scrollIntoView({block:'start'});}
    }
    content.append(element('h3','Cartridges and hydraulic windows'));
    if(!plan.components.length)content.append(element('p','No cartridges in this circuit. A port/distribution block can be generated if the net topology is usable.'));
    for(const component of plan.components){
      const card=element('section',null,'library-card');content.append(card);card.append(element('h4',component.label+(component.model?' · '+component.model:'')));
      const binding=options.bindings[component.id],definition=component.definition;
      if(component.resolution&&!binding){card.append(element('p',component.resolution.message),element('p',component.resolution.action,'property-note'));}
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
      if(port.definition){card.append(element('p','Selected: '+port.definition.label));if(options.port_definitions[port.id]){field(card,'Port definition decision · '+port.label,options.port_definitions[port.id].decision||'',v=>options.port_definitions[port.id].decision=v);action(card,'Clear selected definition · '+port.label,()=>{delete options.port_definitions[port.id];prepare().catch(e=>$('workflow-error').textContent=e.message);});}}
      else if(port.standard)card.append(element('p','REVIEW REQUIRED · This explicit '+port.standard+' requirement needs a complete matching SQLite external-port definition. A straight bore is not equivalent.','error'));
      else{card.append(element('p',port.provisional?'One-off Custom Straight Bore selected; thread and fitting compatibility remain intentionally unresolved.':'No standard identity was supplied. You may explicitly select a one-off Custom Straight Bore with an engineering decision.'));if(port.provisional){field(card,'Provisional straight-bore decision · '+port.label,options.provisional_ports[port.id]||'',v=>options.provisional_ports[port.id]=v);action(card,'Cancel provisional straight bore',()=>{delete options.provisional_ports[port.id];prepare().catch(e=>$('workflow-error').textContent=e.message);});}else action(card,'Choose One-off Custom Straight Bore · '+port.label,()=>{options.provisional_ports[port.id]='';prepare().catch(e=>$('workflow-error').textContent=e.message);});}
      field(card,'Port face · '+port.label,options.port_faces[port.id]||'',v=>{if(v)options.port_faces[port.id]=v;else delete options.port_faces[port.id];},faceOptions);
      librarySearch(card,task,'external-port',port.label,async choice=>{delete options.provisional_ports[port.id];options.port_definitions[port.id]={definition_key:choice.key,definition_sha256:choice.sha256,zone_ports:{},decision:''};await prepare();});
    }
    if(plan.mounting_requirements?.length||options.threaded_mounting_holes.length){const mounting=element('section');content.append(element('h3','Threaded mounting holes'),mounting);mounting.append(element('p','Thread identity and every U/V position are engineer-entered. The generator never invents a bolt pattern.'));for(const [index,row] of options.threaded_mounting_holes.entries()){const card=element('div',null,'library-card'),resolved=plan.mounting_holes?.[index];mounting.append(card);card.append(element('strong',resolved?.thread?.display_name||row.thread_definition_id));field(card,'Face',row.face,v=>row.face=v,faceOptions);field(card,'U / mm',row.u,v=>row.u=v,null,true);field(card,'V / mm',row.v,v=>row.v=v,null,true);field(card,'Drill depth / mm',row.depth,v=>row.depth=v,null,true);field(card,'Thread depth / mm',row.thread_depth,v=>row.thread_depth=v,null,true);field(card,'Termination',String(row.through),v=>row.through=v==='true',{false:'Blind',true:'Through'});action(card,'Remove mounting hole',()=>{options.threaded_mounting_holes.splice(index,1);prepare().catch(e=>$('workflow-error').textContent=e.message);});}
      const editor=element('details');editor.append(element('summary','Add explicitly positioned threaded mounting hole'));mounting.append(editor);api('/api/threads?usable_only=true&limit=500').then(response=>{const preferred=task.inputs?.project_context==='inch'?'UNC':'Metric';let family=response.families.includes(preferred)?preferred:response.families[0]||'',native='',threadId='',face='top',u=0,v=0,depth=20,threadDepth=16,through=false;const draw=()=>{editor.querySelectorAll(':scope > :not(summary)').forEach(node=>node.remove());field(editor,'Thread standard / family',family,value=>{family=value;threadId='';draw();},Object.fromEntries(response.families.map(value=>[value,value])));field(editor,'Native standard',native,value=>{native=value;threadId='';draw();},{'':'All',metric:'Metric-native',inch:'Inch-native'});const rows=response.items.filter(row=>row.normalized_family===family&&(!native||row.unit_system===native));if(!rows.some(row=>row.id===threadId))threadId=rows[0]?.id||'';field(editor,'Thread',threadId,value=>threadId=value,Object.fromEntries(rows.map(row=>[row.id,row.display_name+' · '+row.unit_system+' native'])));field(editor,'Face',face,value=>face=value,faceOptions);field(editor,'U / mm',u,value=>u=value,null,true);field(editor,'V / mm',v,value=>v=value,null,true);field(editor,'Drill depth / mm',depth,value=>depth=value,null,true);field(editor,'Thread depth / mm',threadDepth,value=>threadDepth=value,null,true);field(editor,'Termination',String(through),value=>through=value==='true',{false:'Blind',true:'Through'});action(editor,'Add resolved mounting hole',()=>{if(!threadId)throw Error('Select a source-backed thread.');options.threaded_mounting_holes.push({thread_definition_id:threadId,face,u,v,depth,thread_depth:threadDepth,through});prepare().catch(e=>$('workflow-error').textContent=e.message);});};draw();}).catch(e=>editor.append(element('p',e.message,'error')));field(mounting,'Mounting-hole engineering decision',options.mounting_decision,v=>options.mounting_decision=v);}
    const topology=element('details');topology.open=plan.ports.some(p=>!p.net&&!['blocked','terminated'].includes(p.disposition));topology.append(element('summary','Review / correct hydraulic net assignments'));content.append(topology);
    topology.append(element('p','Net IDs: '+plan.nets.map(n=>n.id+' = '+n.label).join(' · ')));
    for(const port of plan.ports){if(['blocked','terminated'].includes(port.disposition)){topology.append(element('p',(port.component_id?port.component_id+'.':'')+port.label+' · '+port.disposition+' · no hydraulic net required'));continue;}field(topology,'Net · '+(port.component_id?port.component_id+'.':'')+port.label,options.net_overrides[port.id]||port.net||'',v=>{if(v.trim())options.net_overrides[port.id]=v.trim();else delete options.net_overrides[port.id];});}
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
    action(details,'Search library · '+label,safe(async()=>{query=input.value;results.replaceChildren(element('p','Searching all source-native standards; project context controls preference only…'));
      const rows=await api(`/api/ai-design/tasks/${task.id}/library-choices?`+new URLSearchParams({q:query,role}));if(!details.isConnected)return;results.replaceChildren();
      for(const row of rows){const card=element('div',null,'ai-choice');card.append(element('p',`${row.label} · ${row.manufacturer} · ${row.unit} · ${row.geometry_status}`));action(card,'Choose '+row.label,safe(()=>onSelect(row)));results.append(card);}
      if(!rows.length)results.append(element('p','No matches. Refine the native cavity designation or add an engineer-reviewed PMC definition through the existing Library.'));
    }));
  }

  async function generate(task,run){
    if(busy)return;busy=true;
    const token=++screen;
    try{
      content.querySelectorAll('button,input,select,textarea').forEach(e=>e.disabled=true);
      const status=content.querySelector('.ai-job-state');if(status)status.textContent='Checking Library choices, hydraulic windows and requirements…';
      const payload={expected_revision:task.revision,run_id:run.id,options};
      const plan=await post(`/api/ai-design/tasks/${task.id}/generation/preflight`,payload);
      if(token!==screen||!here()||$('workflow-title').textContent!=='AI Design · Create manifold draft')return;
      if(!plan.ready){renderPlan(task,run,plan,true);return;}
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
      content.append(element('p','The draft preserves all failed checks and open engineering decisions. Opening it does not mark it approved. Move, replace, reroute, save, then Validate in the normal Studio.','ai-provider-note'));
      action(content,'Open draft in Manifold Studio',safe(async()=>{const handoff=await inspectGeneratedDraft(packet,post);if(newProject(handoff.design,handoff.definitions,handoff.threads)){$('workflow-dialog').close();ctx.notice('AI Draft opened. Review the linked analysis and engineering decisions, then Save Project or Validate.');}})).classList.add('primary');
      const a=element('a','Download draft project JSON');a.href=`/api/ai-design/tasks/${packet.task_id}/generations/${packet.id}/project`;a.className='download';content.append(a);
      for(const attempt of packet.attempts){content.append(element('p',`Candidate ${attempt.index+1}: ${attempt.error||`${attempt.geometry_failures} geometry failures · ${attempt.counts.FAIL} total FAIL · ${(attempt.failed_rules||[]).join(', ')||'no failed rules'}`}`));}
      const failures=element('details');failures.append(element('summary','Inspect retained exact validation failures'));for(const check of packet.validation.checks.filter(c=>c.status==='FAIL'))failures.append(element('p',`${check.rule} · ${check.items.join(', ')} · ${check.message}`));content.append(failures);
    }
    for(const row of packet.dispositions||[]){const card=element('div',null,'library-card');card.append(element('strong',`${row.property} · ${row.status}`),element('p',row.message));content.append(card);}
    action(content,'Return to analysis',back);
  }
  return {settings,prepare,showPacket};
}
