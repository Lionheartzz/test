import {engineeringText,engineeringName} from './engineering-labels.js';
// Local settings and engineering handoff reuse the normal Studio draft workflow.
import {engineeringFactsUI} from './engineering-facts-ui.js';
export async function inspectGeneratedDraft(packet,post){
  const inspection=await post('/api/import-project',packet.design);
  return {design:inspection.design,definitions:inspection.engineering?.definitions||{},threads:inspection.engineering?.threads||{}};
}

export function aiGeneration(ctx, {open, back, session, refreshTask, watchJob, onPreflight=()=>{}}) {
  const {$,element,field,action,api,post,newProject}=ctx, content=$('workflow-content');
  const faceOptions={'':'Use interpreted requirements / proposal',top:'Top',bottom:'Bottom',left:'Left',right:'Right',front:'Front',back:'Back'};
  let options={},optionRun=null,screen=0,busy=false;
  const searchStates=new Map();
  const here=()=>$('workflow-dialog').open&&$('workflow-title').textContent.startsWith('AI Design');
  const safe=fn=>async()=>{try{await fn();}catch(e){$('workflow-error').textContent=e.message;}};
  function reset(run){if(optionRun!==run.id){optionRun=run.id;searchStates.clear();options={preferred_component_face:null,preferred_port_face:null,bindings:{},port_definitions:{},provisional_ports:{},threaded_mounting_holes:[],mounting_decision:'',net_overrides:{},component_faces:{},port_faces:{},placement_decision:'',drilling_diameter:8,port_diameter:12,port_depth:12,minimum_wall:null,max_attempts:4};}}
  function check(parent,label,value,onChange){const wrap=element('label',null,'ai-check'),input=element('input');input.type='checkbox';input.checked=value;input.setAttribute('aria-label',label);input.onchange=()=>onChange(input.checked);wrap.append(input,document.createTextNode(label));parent.append(wrap);return input;}

  function decisionNavigation(decisions){
    const targets=new Map(),marked=new Set(),links=[];let current=null;
    const key=(section,id,field)=>JSON.stringify([section,id||null,field||null]);
    const matches=(row,section,id,field)=>row.section===section&&(row.target_id||null)===(id||null)&&(!row.field||!field||row.field===field);
    return {
      link(decision,button){links.push({decision,button});button.setAttribute('aria-label',button.textContent+' · '+engineeringText(decision.message));},
      register(section,id,field,root,focus=null,fields=[]){
        root.id||='ai-decision-'+section+'-'+(id||'all');
        targets.set(key(section,id,field),{root,focus});
        for(const {decision,button}of links)if(matches(decision,section,id,field))button.setAttribute('aria-controls',root.id);
        if(!decisions.some(row=>matches(row,section,id,field)))return;
        root.classList.add('ai-decision-required');
        if(!marked.has(root)){
          marked.add(root);const badge=element('strong','Decision required','ai-decision-badge');
          if(root.prepend)root.prepend(badge);else root.append(badge);
        }
        for(const input of fields)(input.closest?.('.field')||input).classList.add('ai-decision-field');
      },
      jump(decision){
        if(decision.section==='analysis'){back();return;}
        const target=targets.get(key(decision.section,decision.target_id,decision.field))
          ||targets.get(key(decision.section,decision.target_id,null))||targets.get(key('requirements',null,null));
        if(!target?.root.isConnected)return;
        const control=(typeof target.focus==='function'?target.focus():target.focus)||target.root;
        for(let node=control;node&&node!==content;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
        current?.classList.remove('ai-decision-current');current=target.root;current.classList.add('ai-decision-current');
        if(control===target.root)control.tabIndex=-1;
        control.focus({preventScroll:true});control.scrollIntoView({block:'center'});
      }
    };
  }

  async function settings(onSaved){
    const token=++screen;open('AI Design · Provider settings');content.classList.add('ai-content');
    content.append(element('p','Configure your own multimodal endpoint and model. Credentials stay in this computer’s private local settings file and are never exported with a project.'));
    const current=await api('/api/ai-design/settings');if(token!==screen||!here()||$('workflow-title').textContent!=='AI Design · Provider settings')return;
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
    action(form,'Save provider settings',safe(async()=>{const raw=tokens.value.trim();if(raw&&(!/^[0-9]+$/.test(raw)||BigInt(raw)<1n))throw Error('Maximum output tokens must be a positive whole number, or blank for the provider default.');value.max_tokens=raw||null;const result=await post('/api/ai-design/settings',value);key.value='';value.api_key='';await onSaved(result);if(here()&&$('workflow-title').textContent==='AI Design · Provider settings')back();}));
    if(current.key_present)action(form,'Forget stored API key',safe(async()=>{await post('/api/ai-design/settings/clear-key',{});await onSaved({ready:false});if(here()&&$('workflow-title').textContent==='AI Design · Provider settings')back();}));
    action(form,'Back to analysis',back);
  }

  async function prepare(autoGenerate=false){
    const {task,run,dirty}=session();if(!task||!run||run.status!=='completed')throw Error('Complete an analysis first.');
    if(dirty)throw Error('Save and analyze your changed inputs first.');
    reset(run);const token=++screen;open('AI Design · Create manifold draft');content.classList.add('ai-content');
    content.append(element('p','Resolving existing library data and engineering requirements…','loading-state'));
    const plan=await post(`/api/ai-design/tasks/${task.id}/generation/preflight`,{expected_revision:task.revision,run_id:run.id,options});
    if(token!==screen||!here()||$('workflow-title').textContent!=='AI Design · Create manifold draft')return;
    onPreflight(task,plan);
    const navigation=renderPlan(task,run,plan);
    if(autoGenerate&&plan.ready)await generate(task,run);
    return navigation;
  }

  function renderPlan(task,run,plan,attempted=false){
    open('AI Design · Create manifold draft');content.classList.add('ai-content');
    const decisions=plan.decisions||plan.blocked.map(message=>({message,section:'requirements'}));
    const navigation=decisionNavigation(decisions);
    action(content,'Back to hydraulic analysis',back);
    content.append(element('p',`${run.provider.is_mock?'MOCK analysis':'AI analysis'} · ${run.provider.id} / ${run.provider.model}. The result will open as an editable Draft, with exact checks and unresolved engineering decisions visible.`,'ai-provider-note'));
    if(plan.blocked.length){const summary=element('section',null,'ai-blocked');summary.setAttribute('role','alert');summary.tabIndex=-1;
      summary.append(element('h3',attempted?`Draft not generated · ${plan.blocked.length} blockers remain`:`Draft generation needs ${plan.blocked.length} decision${plan.blocked.length===1?'':'s'}`),element('p','Resolve the items below, then recheck or generate again. Your saved analysis is retained; no new AI call is needed.'));
      const list=element('ul');for(const decision of decisions){
        const row=element('li',null,'ai-decision-row');row.append(element('span',engineeringText(decision.message)));
        const label=decision.section==='topology'?'Review hydraulic connections':decision.section==='component'?
          decision.field==='mapping'?'Map hydraulic ports':'Choose engineering interface':decision.section==='analysis'?'Review hydraulic analysis':
          decision.section==='mounting'?'Review mounting holes':decision.section==='requirements'?'Review requirements':'Review port definition';
        const button=action(row,label,()=>navigation.jump(decision));button.classList.add('ai-decision-action');navigation.link(decision,button);list.append(row);
      }summary.append(list);content.append(summary);
      if(attempted){summary.focus();summary.scrollIntoView({block:'start'});}
    }
    const placement=element('section',null,'library-card');content.append(placement);placement.append(element('h3','AI generation placement preferences'));const preferences={...faceOptions,'':'Auto'};field(placement,'Preferred valve / cartridge face',options.preferred_component_face||'',v=>options.preferred_component_face=v||null,preferences);field(placement,'Preferred external port face',options.preferred_port_face||'',v=>options.preferred_port_face=v||null,preferences);placement.append(element('p','Used before generation. Existing authored geometry is never moved by these preferences.'));
    content.append(element('h3','Components and engineering interfaces'));
    if(plan.material_engineering_facts)engineeringFactsUI(ctx,content,plan.material_engineering_facts,{title:'Proposed material engineering data'});
    if(!plan.components.length)content.append(element('p','No mounted components in this circuit. A port/distribution block can be generated if the net topology is usable.'));
    for(const component of plan.components){
      const card=element('section',null,'library-card');content.append(card);card.append(element('h4',component.label+(component.model&&component.model!==component.label?' · '+component.model:'')));
      if(component.recognized_interface)card.append(element('p','Recognized machining interface: '+engineeringText(component.recognized_interface)));
      for(const text of component.observed_identity_annotations||[])card.append(element('p','Observed annotation: '+engineeringText(text),'property-note'));
      const conditions=Object.entries(component.recognized_facts||{}).filter(([key,value])=>value!=null&&/pressure|flow|passage|bore/i.test(key));if(conditions.length)card.append(element('p','Recognized schematic: '+conditions.map(([key,value])=>key.replaceAll('_',' ')+': '+value).join(' · ')));
      const binding=options.bindings[component.id],definition=component.definition,contract=component.port_contract;
      const mappingInputs=[],missingMappingInputs=[],candidateButtons=[];
      if(contract){
        card.append(element('p','Library hydraulic ports (fixed): '+contract.physical_ports.map(port=>port.label).join(' · ')));
        if(contract.unassigned_observations.length)card.append(element('p','Unassigned schematic observations: '+contract.unassigned_observations.map(port=>port.label).join(' · '),'review-warning'));
        if(contract.missing_interfaces.length)card.append(element('p','Library ports without a matching schematic observation: '+contract.missing_interfaces.join(' · '),'review-warning'));
      }
      const recognition=element('details');recognition.tabIndex=-1;recognition.append(element('summary','Schematic terminal observations'));card.append(recognition);
      const recognizedPorts=plan.ports.filter(p=>p.component_id===component.id);
      const countMismatch=contract?.status==='port_count_conflict';
      recognition.open=countMismatch;
      if(countMismatch)recognition.append(element('p',`The analysis reports ${recognizedPorts.length} schematic observations; the library fixes ${contract.physical_port_count} physical ports. Review the unmatched observations without changing the library port set.`,'review-warning'));
      for(const port of recognizedPorts){const row=element('div',null,'ai-choice');row.append(element('span',`${port.label} → ${plan.nets.find(net=>net.id===port.net)?.label||'Unknown net'}`));recognition.append(row);
        action(row,'Exclude incorrect observation '+port.label,safe(()=>correctPort(task,run,plan,port.id,true,component.id))).disabled=recognizedPorts.length<=1;
      }
      for(const port of (plan.excluded_ports||[]).filter(p=>p.component_id===component.id)){
        const row=element('div',null,'ai-choice');row.append(element('span','Excluded schematic observation '+port.label));recognition.append(row);
        action(row,'Restore observation '+port.label,safe(()=>correctPort(task,run,plan,port.id,false,component.id)));
      }
      const choice=component.choices.find(row=>row.cartridge_id===component.cartridge_id);
      if(choice?.engineering_facts)engineeringFactsUI(ctx,card,choice.engineering_facts,{title:'Cartridge engineering data'});
      if(component.resolution&&!binding){card.append(element('p',engineeringText(component.resolution.message)),element('p',engineeringText(component.resolution.action),'property-note'));}
      if(definition){
        card.append(element('p',`${definition.display_label||definition.label} · ${definition.unit} · ${definition.usable?'Available':'Machining definition incomplete'}`));
        if(component.automatic)card.append(element('p','Engineering interface and hydraulic port labels matched. Review the editable draft before production.'));
        const ports=Object.fromEntries(plan.ports.filter(p=>p.component_id===component.id).map(p=>[p.id,`${p.label} → ${plan.nets.find(n=>n.id===p.net)?.label||'Unknown net'}`]));
        for(const zone of definition.zones){
          const label=`${component.label} · fixed library port ${zone.display_label||zone.id} → schematic observation`;
          if(binding||!component.automatic){const selected=(binding?.zone_ports||component.mapping)[zone.id]||'',input=field(card,label,selected,v=>{
              const selectedBinding=options.bindings[component.id]??={definition_key:definition.key,definition_sha256:definition.sha256,zone_ports:{...component.mapping},decision:''};
              if(v)selectedBinding.zone_ports[zone.id]=v;else delete selectedBinding.zone_ports[zone.id];
            },{'':'Choose an observation',...ports});mappingInputs.push(input);
            if(!ports[selected]||Object.values(binding?.zone_ports||component.mapping).filter(value=>value===selected).length!==1)missingMappingInputs.push(input);}
          else card.append(element('p',label+': '+(ports[component.mapping[zone.id]]||'Unmapped')));
        }
        if(definition.zones.length!==Object.keys(ports).length){
          card.append(element('p',`The library fixes ${definition.zones.length} hydraulic ports; ${Object.keys(ports).length} schematic observations were read. Resolve the observation conflict before generation.`,'review-warning'));
          missingMappingInputs.push(...mappingInputs);
        }
      }else card.append(element('p','Select the machining interface used by this component. Existing cartridge cavities, surface-mounted valve interfaces and other source-defined engineering families use the same catalogue; confirm the hydraulic port mapping and orientation.'));
      const interfaceChoices=definition?element('details'):card;
      if(definition){interfaceChoices.append(element('summary','Change engineering interface (optional)'));card.append(interfaceChoices);}
      for(const choice of component.choices){
        const candidate=element('div',null,'library-candidate');interfaceChoices.append(candidate);
        candidate.append(element('p',[choice.display_label||choice.label,choice.unit,choice.definition_origin,
          choice.machining_depth_mm!=null?'Machining depth '+Number(choice.machining_depth_mm.toFixed(3))+' mm':'',
          choice.usable?'Available':'Machining definition incomplete'].filter(Boolean).join(' · ')));
        if(choice.usable)candidateButtons.push(action(candidate,'Use candidate '+(choice.display_label||choice.label)+' · '+choice.unit,safe(()=>selectCavity(component,choice,plan))));
        else if(choice.unusable_reason)candidate.append(element('p',engineeringText(choice.unusable_reason),'property-note'));
      }
      const search=librarySearch(interfaceChoices,task,'component-interface',component.label,choice=>selectCavity(component,choice,plan));
      navigation.register('component',component.id,'interface',card,()=>candidateButtons[0]||search.input,[search.input]);
      navigation.register('component',component.id,'mapping',card,()=>countMismatch?recognition:missingMappingInputs[0]||mappingInputs[0]||candidateButtons[0]||search.input,missingMappingInputs);
      field(card,'Mounting face · '+component.label,options.component_faces[component.id]||'',v=>{if(v)options.component_faces[component.id]=v;else delete options.component_faces[component.id];},faceOptions);
    }
    content.append(element('h3','External ports'));
    const grouped=new Set(),groupEditors=new Map();
    for(const group of plan.external_port_groups||[]){
      if(!group.normalized)continue;
      const rows=plan.external_ports.filter(p=>group.port_ids.includes(p.id));
      const selected=rows.every(p=>options.port_definitions[p.id])&&new Set(rows.map(p=>options.port_definitions[p.id].definition_key)).size===1;
      const card=element('section',null,'library-card'),thread=group.thread_resolution;content.append(card);card.append(element('h4',group.labels.join(', ')));
      const ids=group.port_ids;ids.forEach(id=>grouped.add(id));
      if(thread?.recognized){
        card.append(element('p','Thread: '+thread.label+(thread.definition?' · recognized':' · needs source resolution')));
        if(!thread.definition)card.append(element('p','No unique usable thread definition was resolved; review the thread identity/source data.','review-warning'));
        card.append(element('p','Port machining / sealing form: '+(selected?rows[0].definition.label:rows.some(p=>p.definition)?'Selected individually below':'Not specified by schematic')));
        if(rows.some(p=>p.state==='thread_defined'))card.append(element('p','Thread-defined ports can enter an editable Draft. Thread depth, sealing, complete machining and installation clearance remain unresolved.','property-note'));
      }else card.append(element('p','Source specification: '+group.specification),element('p',group.canonical?'Resolved complete definition: '+group.canonical.label:'Select a complete machining definition or review the source standard.'));
      if(selected)action(card,'Clear complete definition · '+group.specification,()=>{for(const id of ids)delete options.port_definitions[id];prepare().catch(e=>$('workflow-error').textContent=e.message);});
      const refinement=element('details');refinement.open=!!group.unresolved_ids.length&&!thread?.definition;
      refinement.append(element('summary',thread?.recognized?'Optional: Select complete port machining definition':'Select complete port machining definition'));card.append(refinement);
      refinement.append(element('p','These definitions add a complete machining / sealing form. They are not alternative interpretations of the thread requirement.'));
      const select=async choice=>{for(const id of ids){delete options.provisional_ports[id];options.port_definitions[id]={definition_key:choice.key,definition_sha256:choice.sha256,zone_ports:{},decision:''};}await prepare();};
      for(const choice of group.choices)action(refinement,'Use '+choice.label+' · '+choice.unit,safe(()=>select(choice)));
      const search=librarySearch(refinement,task,'external-port',group.specification,select);
      groupEditors.set(group.id,{card,search});
      navigation.register('port_group',group.id,'interface',card,search.input,[search.input]);
    }

    for(const port of plan.external_ports){
      const card=element('section',null,'library-card');content.append(card);card.append(element('h4',port.label),element('p','Schematic specification: '+(port.specification||'Unknown')));
      if(port.definition){card.append(element('p','Complete machining definition: '+port.definition.label));if(options.port_definitions[port.id])action(card,'Clear selected definition · '+port.label,()=>{delete options.port_definitions[port.id];prepare().catch(e=>$('workflow-error').textContent=e.message);});}
      else if(port.state==='thread_defined')card.append(element('p','Thread: '+port.resolution.thread_resolution.label+' · recognized'),element('p','Port machining / sealing form: Not specified by schematic','property-note'));
      else if(port.standard&&!grouped.has(port.id))card.append(element('p','REVIEW REQUIRED · This explicit '+port.standard+' requirement needs matching defined engineering data. A straight bore is not equivalent.','error'));
      else if(!port.standard){card.append(element('p',port.provisional?'One-off Custom Straight Bore selected; thread and fitting compatibility remain intentionally unresolved.':'No standard identity was supplied. You may explicitly select a one-off Custom Straight Bore with an engineering decision.'));if(port.provisional){field(card,'Provisional straight-bore decision · '+port.label,options.provisional_ports[port.id]||'',v=>options.provisional_ports[port.id]=v);action(card,'Cancel provisional straight bore',()=>{delete options.provisional_ports[port.id];prepare().catch(e=>$('workflow-error').textContent=e.message);});}else action(card,'Choose One-off Custom Straight Bore · '+port.label,()=>{options.provisional_ports[port.id]='';prepare().catch(e=>$('workflow-error').textContent=e.message);});}
      field(card,'Port face · '+port.label,options.port_faces[port.id]||'',v=>{if(v)options.port_faces[port.id]=v;else delete options.port_faces[port.id];},faceOptions);
      const search=!grouped.has(port.id)?librarySearch(card,task,'external-port',port.label,async choice=>{delete options.provisional_ports[port.id];options.port_definitions[port.id]={definition_key:choice.key,definition_sha256:choice.sha256,zone_ports:{},decision:''};await prepare();}):null;
      const groupEditor=groupEditors.get(port.group_id),decisionInput=card.querySelector?.('input[aria-label^="Provisional straight-bore decision"]');
      navigation.register('external_port',port.id,'interface',groupEditor?.card||card,groupEditor?.search.input||search?.input);
      navigation.register('external_port',port.id,'decision',card,decisionInput,decisionInput?[decisionInput]:[]);
    }
    if(plan.mounting_requirements?.length||options.threaded_mounting_holes.length){const mounting=element('section');content.append(element('h3','Threaded mounting holes'),mounting);mounting.append(element('p','Thread identity and every U/V position are engineer-entered. The generator never invents a bolt pattern.'));for(const [index,row] of options.threaded_mounting_holes.entries()){const card=element('div',null,'library-card'),resolved=plan.mounting_holes?.[index];mounting.append(card);card.append(element('strong',resolved?.thread?.display_name||'Thread'));field(card,'Face',row.face,v=>row.face=v,faceOptions);field(card,'U / mm',row.u,v=>row.u=v,null,true);field(card,'V / mm',row.v,v=>row.v=v,null,true);field(card,'Drill depth / mm',row.depth,v=>row.depth=v,null,true);field(card,'Thread depth / mm',row.thread_depth,v=>row.thread_depth=v,null,true);field(card,'Termination',String(row.through),v=>row.through=v==='true',{false:'Blind',true:'Through'});action(card,'Remove mounting hole',()=>{options.threaded_mounting_holes.splice(index,1);prepare().catch(e=>$('workflow-error').textContent=e.message);});}
      const editor=element('details');editor.append(element('summary','Add explicitly positioned threaded mounting hole'));mounting.append(editor);api('/api/threads?usable_only=true&limit=500').then(response=>{const preferred=task.inputs?.project_context==='inch'?'UNC':'Metric';let family=response.families.includes(preferred)?preferred:response.families[0]||'',native='',threadId='',face='top',u=0,v=0,depth=20,threadDepth=16,through=false;const draw=()=>{editor.querySelectorAll(':scope > :not(summary)').forEach(node=>node.remove());field(editor,'Thread standard / family',family,value=>{family=value;threadId='';draw();},Object.fromEntries(response.families.map(value=>[value,value])));field(editor,'Native standard',native,value=>{native=value;threadId='';draw();},{'':'All',metric:'Metric-native',inch:'Inch-native'});const rows=response.items.filter(row=>row.normalized_family===family&&(!native||row.unit_system===native));if(!rows.some(row=>row.id===threadId))threadId=rows[0]?.id||'';field(editor,'Thread',threadId,value=>threadId=value,Object.fromEntries(rows.map(row=>[row.id,row.display_name+' · '+row.unit_system+' native'])));field(editor,'Face',face,value=>face=value,faceOptions);field(editor,'U / mm',u,value=>u=value,null,true);field(editor,'V / mm',v,value=>v=value,null,true);field(editor,'Drill depth / mm',depth,value=>depth=value,null,true);field(editor,'Thread depth / mm',threadDepth,value=>threadDepth=value,null,true);field(editor,'Termination',String(through),value=>through=value==='true',{false:'Blind',true:'Through'});action(editor,'Add resolved mounting hole',()=>{if(!threadId)throw Error('Select a defined thread.');options.threaded_mounting_holes.push({thread_definition_id:threadId,face,u,v,depth,thread_depth:threadDepth,through});prepare().catch(e=>$('workflow-error').textContent=e.message);});};draw();}).catch(e=>editor.append(element('p',e.message,'error')));const mountingDecision=field(mounting,'Mounting-hole engineering decision',options.mounting_decision,v=>options.mounting_decision=v);navigation.register('mounting',null,'decision',mounting,mountingDecision,[mountingDecision]);navigation.register('mounting',null,null,mounting,()=>mounting.querySelector('input,select'));}
    if(plan.mounting_requirements?.length>1){
      const assignment=element('section');content.append(assignment);assignment.append(element('h4','Mounting requirement assignments'));
      const choices=Object.fromEntries([['','Unassigned'],...plan.mounting_requirements.map(row=>[row.intent_id,row.mounting?.thread_designation||'Mounting requirement'])]);
      options.threaded_mounting_holes.forEach((hole,index)=>field(assignment,'Hole '+(index+1)+' requirement',hole.requirement_id||'',value=>{hole.requirement_id=value||null;},choices));
    }
    const topology=element('details');const uncertainConnections=plan.nets.some(net=>net.status==='uncertain');topology.open=uncertainConnections||plan.ports.some(p=>!p.net&&!['blocked','terminated'].includes(p.disposition));topology.append(element('summary','Review / correct hydraulic net assignments'));content.append(topology);
    if(uncertainConnections)topology.append(element('p','Review these proposed connections against the schematic. Generate editable 3D draft uses the current assignments.','review-warning'));
    topology.append(element('p','Hydraulic lines: '+plan.nets.map(n=>n.label).join(' · ')));
    for(const port of plan.ports){const owner=plan.components.find(c=>c.id===port.component_id)?.label,name=(owner?owner+' · ':'')+port.label;if(['blocked','terminated'].includes(port.disposition)){topology.append(element('p',name+' · '+port.disposition+' · no hydraulic net required'));continue;}
      const input=field(topology,'Net · '+name,options.net_overrides[port.id]||plan.nets.find(n=>n.id===port.net)?.label||'',v=>{if(v.trim())options.net_overrides[port.id]=v.trim();else delete options.net_overrides[port.id];});
      navigation.register('topology',port.id,'net',topology,input,[input]);
    }
    navigation.register('topology',null,'decision',topology,()=>topology.querySelector('input'));
    field(content,'Placement override decision',options.placement_decision,v=>options.placement_decision=v).placeholder='Required only when overriding proposed component/port faces';
    const dimensions=element('details');dimensions.append(element('summary','Draft geometry assumptions'));content.append(dimensions);
    for(const [key,label]of [['drilling_diameter','Minimum proposed drilling diameter (mm)'],['port_diameter','Custom Straight Bore diameter (mm)'],['port_depth','Draft entry depth for thread-only / custom ports (mm)']])field(dimensions,label,options[key],v=>options[key]=v,null,true);
    dimensions.append(element('p','Generate creates one editable project. Open it in Model to use shared automatic routing, then explicitly Optimize or Validate. Project limits remain 120 features and 40 hydraulic nets.'));
    dimensions.append(element('p','Entry depth and drill point are editable Draft proposals, not confirmed machining dimensions. Thread-only tap-drill diameter comes from engineering library; thread depth and the complete port form remain unresolved. Flow requirements may increase routing drilling size. Cavity geometry is never resized.'));
    const requirements=element('section');requirements.append(element('h3','How your requirements will be used'));content.append(requirements);
    for(const row of plan.dispositions){const card=element('div',null,'library-card');card.append(element('strong',`${row.property} · ${row.status.replaceAll('_',' ')}`),element('p',row.message));requirements.append(card);}
    navigation.register('requirements',null,null,requirements);
    const controls=element('div',null,'action-row');content.append(controls);
    action(controls,'Recheck choices and requirements',safe(()=>prepare()));
    action(controls,'Generate editable 3D draft',safe(()=>generate(task,run)));
    const progress=element('div','', 'ai-job-state');progress.setAttribute('role','status');content.append(progress);
    return navigation;
  }

  async function selectCavity(component,choice,plan){
    const ports=plan.ports.filter(p=>p.component_id===component.id),mapping={};
    for(const zone of choice.zones){const normalized=(zone.display_label||zone.id).toLowerCase().replace(/^port/,'');const matches=ports.filter(p=>p.label.toLowerCase().replace(/^port/,'')===normalized);if(matches.length===1)mapping[zone.id]=matches[0].id;}
    options.bindings[component.id]={definition_key:choice.key,definition_sha256:choice.sha256,zone_ports:mapping,decision:''};
    const navigation=await prepare();navigation?.jump({section:'component',target_id:component.id,field:'mapping'});
  }

  async function correctPort(task,run,plan,portId,exclude,componentId){
    const token=screen;
    const excluded=new Set(plan.port_corrections?.excluded_port_ids||[]),overrides={...plan.port_corrections?.net_overrides};
    if(exclude){excluded.add(portId);delete overrides[portId];}else excluded.delete(portId);
    const response=await post(`/api/ai-design/tasks/${task.id}/port-corrections`,{expected_revision:task.revision,run_id:run.id,excluded_port_ids:[...excluded],net_overrides:overrides});
    await refreshTask(task.id);run.port_corrections=response.port_corrections;run.reviewed_result=response.reviewed_result;
    if(token!==screen||!here()||$('workflow-title').textContent!=='AI Design · Create manifold draft'||session().task?.id!==task.id)return;
    delete options.net_overrides[portId];
    for(const binding of Object.values(options.bindings))for(const [zone,port]of Object.entries(binding.zone_ports))if(excluded.has(port))delete binding.zone_ports[zone];
    const navigation=await prepare();navigation?.jump({section:'component',target_id:componentId,field:'mapping'});
  }

  function librarySearch(parent,task,role,label,onSelect){
    const stateKey=JSON.stringify([role,label]),state=searchStates.get(stateKey)||{query:'',open:false};searchStates.set(stateKey,state);
    const details=element('details');details.append(element('summary',role==='external-port'?'Search complete port machining definitions':'Search cavities / valve mounting interfaces'));parent.append(details);
    details.open=state.open;details.ontoggle=()=>{state.open=details.open;};
    let request=0;const input=field(details,'Library search · '+label,state.query,v=>state.query=v),results=element('div');input.type='search';input.placeholder=role==='external-port'?'Port name or standard':'Engineering interface name, family or mounting standard';results.setAttribute('role','status');details.append(results);
    input.addEventListener('input',()=>{state.query=input.value;});
    const search=async()=>{const token=++request;state.query=input.value;results.replaceChildren(element('p','Searching all source-native standards; project context controls preference only…'));
      try{
        const rows=await api(`/api/ai-design/tasks/${task.id}/library-choices?`+new URLSearchParams({q:state.query,role}));if(token!==request||!details.isConnected)return;results.replaceChildren();
        for(const row of rows){const card=element('div',null,'ai-choice'),name=row.display_label||row.label;card.append(element('p',`${name} · ${row.family||row.manufacturer} · ${row.unit} · ${row.usable?'Available':'Machining definition incomplete'}`));
          if(role!=='external-port'&&row.zones?.length)card.append(element('p','Hydraulic interfaces: '+row.zones.map(zone=>zone.display_label||zone.id).join(' · ')));
          const choose=action(card,'Choose '+name,safe(()=>onSelect(row)));choose.disabled=!row.usable;if(!row.usable&&row.unusable_reason)card.append(element('p',row.unusable_reason,'property-note'));results.append(card);
        }
        if(!rows.length)results.append(element('p','No matches. Refine the cavity or mounting-interface designation, or add an engineer-reviewed PMC definition through the existing Library.'));
      }catch(e){if(token===request&&details.isConnected)results.replaceChildren(element('p',e.message,'error'));}
    };
    action(details,'Search library · '+label,search);
    input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing&&!event.repeat){event.preventDefault();event.stopPropagation();search();}});
    return {details,input};
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
      const cancel=action(content,'Cancel generation',safe(async()=>{await post(`/api/ai-design/jobs/${job.id}/cancel`,{});cancel.disabled=true;progress.dataset.cancelling='true';const stage=progress.querySelector('[data-validate-stage]');if(stage)stage.textContent='Stopping local CAD work; retaining the latest authored draft…';}));
      const result=await watchJob(job,progress);
      await refreshTask(task.id);
      if(token===screen&&session().task?.id===task.id&&here()&&$('workflow-title').textContent==='AI Design · Create manifold draft')showPacket(result);
    }finally{busy=false;if(here())content.querySelectorAll('button,input,select,textarea').forEach(e=>e.disabled=false);}
  }

  function showPacket(packet){
    open('AI Design · Generated manifold draft');content.classList.add('ai-content');
    content.append(element('h3',packet.status==='draft'?'Your editable manifold draft':'Generation needs review'),element('p',packet.message||packet.status));
    if(packet.design){
      if(packet.validation)content.append(element('p',`Exact report: ${packet.validation.counts.PASS} PASS · ${packet.validation.counts.WARNING} WARNING · ${packet.validation.counts.FAIL} FAIL. Geometry failures: ${packet.geometry_failures}.`,'ai-summary'));
      else content.append(element('p','Initial project ready · not routed or validated. Open it in Model to start the shared route proposal. You can edit and Save Draft while routing runs.','ai-summary'));
      content.append(element('p','The draft preserves all failed checks and open engineering decisions. Opening it does not mark it approved. Move, replace, reroute, save, then Validate in the normal Studio.','ai-provider-note'));
      action(content,'Open draft in Manifold Studio',safe(async()=>{const handoff=await inspectGeneratedDraft(packet,post);if(newProject(handoff.design,handoff.definitions,handoff.threads)){$('workflow-dialog').close();ctx.notice('AI Draft opened. Review the linked analysis and engineering decisions, then Save Project or Validate.');}})).classList.add('primary');
      const a=element('a','Download draft project JSON');a.href=`/api/ai-design/tasks/${packet.task_id}/generations/${packet.id}/project`;a.className='download';content.append(a);
      for(const attempt of packet.attempts){content.append(element('p',`Candidate ${attempt.index+1}: ${attempt.error||`${attempt.geometry_failures} geometry failures · ${attempt.counts.FAIL} total FAIL · ${(attempt.failed_rules||[]).join(', ')||'no failed rules'}`}`));}
      if(packet.validation){const failures=element('details');failures.append(element('summary','Inspect retained exact validation failures'));for(const check of packet.validation.checks.filter(c=>c.status==='FAIL'))failures.append(element('p',`${check.rule} · ${check.items.join(', ')} · ${check.message} · Actual: ${check.actual??'unavailable'} · Required: ${check.required??'review engineering definition'}`));content.append(failures);}
    }
    for(const row of packet.dispositions||[]){const card=element('div',null,'library-card');card.append(element('strong',`${row.property} · ${row.status}`),element('p',row.message));content.append(card);}
    action(content,'Return to analysis',back);
  }
  return {settings,prepare,showPacket};
}
