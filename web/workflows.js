import {aiDesign} from './ai-design.js';
import {isCavity} from './definition-role.js';
import {customPort,portSetup} from './port-setup.js';
import {guided} from './guided.js';
import {libraryUI} from './library-ui.js';
import {projectUI} from './project-ui.js';
import {clamp,syncNets,featureLabel,returnNetToAutomatic} from './kinematics.js';
import {hydrateDesign} from './domain.js';
import {displayMemberName,displayNetName,displayInterfaceName} from './presentation.js';

function flowSizing(net,standardDrills){
  if(!net.flow_lpm)return {required:null,selected:null};
  const area=net.flow_lpm*1000/60/(net.velocity_limit||6),required=Math.sqrt(4*area/Math.PI);
  return {required,selected:[...(standardDrills||[])].sort((a,b)=>a-b).find(value=>Math.PI*value*value/4+1e-9>=area)||null};
}

export function workflows(ctx){
  const {adoptRoute,replaceCavity,$,element,field,action,api,post,get,state,change,set,newId,select,notice,resolved}=ctx;
  const content=$('workflow-content'),dialog=$('workflow-dialog');
  const guard=fn=>async()=>{try{await fn();$('workflow-error').textContent='';}catch(e){$('workflow-error').textContent=e.message;}};
  function open(title){$('workflow-title').textContent=title;content.replaceChildren();$('workflow-error').textContent='';if(!dialog.open)dialog.showModal();}
  $('workflow-close').onclick=()=>dialog.close();
  const definitions=()=>Object.fromEntries((get().library||[]).map(d=>[d.id,d]));
  function remember(def){if(!get().library.some(row=>row.id===def.id))get().library.push(structuredClone(def));}

  function insertNow(def,face='top',mapping=null,index=0){
    if(!isCavity(def)||!def.usable)throw Error(def.unusable_reason||'Select a usable cavity definition.');
    const ok=change(()=>{const d=get();remember(def);const f={id:newId('CV'),kind:'cavity',face,u:d.block.length/2+index*(def.clearance_diameter+5),v:d.block.width/2,cavity_id:def.id,port_definition_id:null,interface_nets:mapping||Object.fromEntries(def.zones.map((z,i)=>[z.id,d.nets[i%d.nets.length]?.id||'P'])),connects_to:[],suppressed:false,rotation:0,cartridge_id:null,schematic_id:'',parent_id:null,local_offset:[0,0],machining_id:''};[f.u,f.v]=clamp(f,d,f.u,f.v);d.features.push(f);syncNets(d);select(f.id);});
    if(ok)dialog.close();else $('workflow-error').textContent=$('notice').textContent;
  }
  function insert(def){
    let face='top',quantity=1;const mapping=Object.fromEntries(def.zones.map((z,i)=>[z.id,get().nets[i%get().nets.length]?.id||'P']));
    open('Place '+def.label);content.append(element('p','This places the selected cavity ID. Cartridge assignment and schematic intent remain empty unless you add them explicitly.'));
    field(content,'Quantity',quantity,v=>quantity=v,null,true);field(content,'Mounting face',face,v=>face=v,Object.fromEntries(['top','bottom','front','back','left','right'].map(x=>[x,x])));
    for(const z of def.zones)field(content,'Interface '+z.id+' → Net',mapping[z.id],v=>mapping[z.id]=v,Object.fromEntries(get().nets.map(n=>[n.id,n.id])));
    action(content,'Add cavities to draft',()=>{if(!Number.isInteger(quantity)||quantity<1||quantity>20){$('workflow-error').textContent='Quantity must be 1–20.';return;}for(let i=0;i<quantity;i++)insertNow(def,face,{...mapping},i);});
  }

  const library=libraryUI(ctx,{open,insert,onCustomSaved:remember});
  projectUI(ctx);
  guided(ctx,open,library,nets);
  $('library-open').onclick=guard(library);

  $('add-mounting').onclick=()=>{
    let face='top',diameter=12,depth=20,through=false;
    open('Add plain mounting hole');field(content,'Face',face,v=>face=v,{top:'Top',bottom:'Bottom',front:'Front',back:'Back',left:'Left',right:'Right'});
    field(content,'Diameter / mm',diameter,v=>diameter=v,null,true);field(content,'Blind cylinder depth / mm',depth,v=>depth=v,null,true);field(content,'Hole termination',String(through),v=>through=v==='true',{false:'Blind',true:'Through block'});
    content.append(element('p','Creates an explicit non-hydraulic plain bore. Thread geometry and fastener compatibility are not inferred.'));
    action(content,'Add mounting hole',guard(async()=>{const baseline=JSON.stringify(get()),d=structuredClone(get()),dims=[d.block.length,d.block.width,d.block.height],axes={top:[0,1,2],bottom:[0,1,2],front:[0,2,1],back:[0,2,1],left:[1,2,0],right:[1,2,0]}[face],id='MNT_'+crypto.randomUUID().replaceAll('-','');
      d.features.push({id,kind:'mounting',face,u:dims[axes[0]]/2,v:dims[axes[1]]/2,diameter,depth:through?dims[axes[2]]:depth,through,tip_angle:through?180:118});
      const checked=await post('/api/check-design',d);if(JSON.stringify(get())!==baseline)throw Error('Draft changed while adding mounting hole. Retry.');if(change(()=>set(hydrateDesign(checked,definitions())))){select(id);dialog.close();notice('Mounting hole added. Position it and Validate before drawing.');}
    }));
  };

  $('add-port').onclick=()=>{
    const p=customPort();let net=get().nets[0]?.id||'P';
    const render=()=>{open('Add external port');field(content,'Hydraulic net',net,v=>{net=v;render();},Object.fromEntries(get().nets.map(n=>[n.id,n.id])));portSetup(ctx,content,p,net,render);
      action(content,'Add port to draft',guard(async()=>{if(p.mode!=='custom'&&!p.definition)throw Error('Select a machining definition first.');const baseline=JSON.stringify(get()),d=structuredClone(get()),id='PORT_'+crypto.randomUUID().replaceAll('-','');
        const f={id,kind:'port',face:p.face,u:0,v:0,circuit:net,diameter:p.diameter,depth:p.depth,clearance_diameter:p.clearance,size:p.size.slice(0,80),port_type:p.definition?p.definition.label:'Custom straight bore'};
        if(p.definition){remember(p.definition);f.port_definition_id=p.definition.id;f.diameter=Math.min(...p.definition.stages.map(x=>x.diameter));f.depth=p.definition.zones[0].end;f.clearance_diameter=p.definition.clearance_diameter;f.clearance_height=p.definition.clearance_height;f.tip_angle=180;}
        const axes={top:['length','width'],bottom:['length','width'],left:['width','height'],right:['width','height'],front:['length','height'],back:['length','height']}[p.face];[f.u,f.v]=clamp(f,get(),get().block[axes[0]]/2,get().block[axes[1]]/2);d.features.push(f);syncNets(d);
        const checked=await post('/api/check-design',d);if(JSON.stringify(get())!==baseline)throw Error('Draft changed while preparing the port. Retry.');if(change(()=>set(hydrateDesign(checked,definitions())))){select(id);dialog.close();notice('External port added. Review position and fitting installation.');}
      }));
    };render();
  };

  function netMembers(d,netId){const members=[];for(const f of d.features){if(f.suppressed)continue;if(f.kind==='cavity'){for(const [id,net]of Object.entries(f.interface_nets||{}))if(net===netId)members.push(f.id+':'+id);}else if(f.kind==='port'&&f.circuit===netId)members.push(f.id);}return members;}
  function nets(){
    open('Hydraulic Nets · intent and derived connections');content.append(element('p','Net members are derived from cavity interface assignments and external ports. Automatic routing proposes geometry; exact validation decides whether it is acceptable.'));
    action(content,'Reset all routes to automatic',guard(async()=>{if(!confirm('This will remove manual/frozen routing geometry and return all hydraulic nets to automatic routing. Continue?'))return;const d=await post('/api/adopt-routing',get());change(()=>set(hydrateDesign(d,definitions())));nets();}));
    action(content,'Optimize routes with exact checks',guard(async()=>{if(!state().project_id)throw Error('Save Project before running exact route optimization.');const baseline=JSON.stringify(get());const r=await post('/api/optimize-routes',{design:get(),project_id:state().project_id,expected_revision:state().revision,max_attempts:6});if(JSON.stringify(get())!==baseline)throw Error('Draft changed during optimization.');change(()=>set(hydrateDesign(r.design,definitions())));nets();content.prepend(element('p',`${r.attempts.length} exact candidates · FAIL ${r.baseline.FAIL} → ${r.final.FAIL}. Validate to commit.`));}));
    const newNet=element('div',null,'action-row'),name=element('input');name.setAttribute('aria-label','New net ID');name.placeholder='NET_P';newNet.append(name);action(newNet,'Add net',()=>{if(!/^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(name.value)||get().nets.some(n=>n.id===name.value)){$('workflow-error').textContent='Use a unique engineering ID';return;}change(()=>get().nets.push({id:name.value,label:name.value,routing:'automatic',diameter:8}));nets();});content.append(newNet);
    for(const n of get().nets){const card=element('section',null,'library-card'),members=netMembers(get(),n.id);content.append(card);card.append(element('h3',n.label||n.id),element('p',members.map(member=>displayMemberName(get(),member)).join(' ↔ ')||'No interfaces assigned'));const edit=(label,value,fn,o=null,num=false)=>field(card,label,value,v=>{if(change(()=>fn(v)))nets();},o,num);
      edit('Net label · '+n.id,n.label||n.id,v=>n.label=v);
      const colorWrap=element('label','Display color · '+n.id,'field'),color=element('input');color.type='color';color.setAttribute('aria-label','Display color · '+n.id);color.value=n.color||'#b08bea';color.onchange=()=>{if(change(()=>n.color=color.value))nets();};colorWrap.append(color);card.append(colorWrap);
      edit('Diameter sizing · '+n.id,n.diameter_mode||'automatic',v=>{n.diameter_mode=v;n.routing_variant=null;},{automatic:'Automatic from flow',manual:'Engineer override'});
      const sizing=flowSizing(n,get().constraints.standard_drills);
      if(n.diameter_mode==='automatic'){
        card.append(element('p',sizing.required==null?'Enter flow to calculate the required passage diameter.':`Calculated minimum: ${sizing.required.toFixed(2)} mm · ${sizing.selected?`Selected standard drill: Ø${sizing.selected.toFixed(2)} mm`:'No available standard drill is large enough.'}`,'property-note'));
        const effective=field(card,'Effective drill diameter · '+n.id,sizing.selected==null?'Unresolved':sizing.selected.toFixed(2),()=>{});effective.disabled=true;
      }else edit('Engineer override drill diameter · '+n.id,n.diameter,v=>{n.diameter=v;n.routing_variant=null;},null,true);
      edit('Velocity limit m/s · '+n.id,n.velocity_limit||6,v=>{n.velocity_limit=v;n.routing_variant=null;},null,true);edit('Drilling mode · '+n.id,n.drilling_mode||'orthogonal',v=>{n.drilling_mode=v;n.routing_variant=null;},{orthogonal:'Orthogonal only','allow-angled':'Allow angled proposals',simplest:'Prefer simplest manufacturable proposal'});edit('First routing axis · '+n.id,n.preferred_axis||'auto',v=>{n.preferred_axis=v;n.routing_variant=null;},{auto:'Compare all axes',x:'X',y:'Y',z:'Z'});edit('Entry preference · '+n.id,n.entry_preference||'nearest',v=>{n.entry_preference=v;n.routing_variant=null;},{nearest:'Nearest / reuse port',negative:'Negative face',positive:'Positive face'});edit('Flow L/min · '+n.id,n.flow_lpm,v=>{n.flow_lpm=v||null;n.routing_variant=null;},null,true);edit('Pressure bar · '+n.id,n.pressure_bar,v=>n.pressure_bar=v||null,null,true);
      if(n.routing==='automatic')action(card,'Refine / Freeze '+displayNetName(get(),n.id)+' for manual editing',guard(async()=>{if(await adoptRoute(n.id))nets();else throw Error($('notice').textContent);}));
      else action(card,'Return '+displayNetName(get(),n.id)+' to automatic routing',()=>{change(()=>returnNetToAutomatic(get(),n.id));nets();});
    }
    const route=resolved();if(route){const details=element('details');details.append(element('summary','Inspect generated drilling coordinates'));for(const f of route.features.filter(f=>f.route_net)){const row=element('div',null,'port-row');row.append(element('p',`${featureLabel(f,route)} · ${displayNetName(route,f.route_net)} · ${f.face} U${f.u.toFixed(2)} V${f.v.toFixed(2)} · Ø${f.diameter} × ${f.depth.toFixed(2)}`));action(row,'Refine / Edit in 3D',guard(async()=>{if(await adoptRoute(f.route_net,f.id))dialog.close();else throw Error($('notice').textContent);}));details.append(row);}content.append(details);}
  }
  $('nets-open').onclick=nets;

  function schematic(){
    open('Schematic Intent');const d=get(),intent=d.schematic_intent;
    content.append(element('p',intent?'Schematic conformance applies because this project contains explicit intent.':'This project has no schematic intent. Cavity placement alone does not create schematic components or conformance requirements.'));
    const input=element('input');input.type='file';input.accept='.pdf,.png,.jpg,.jpeg';input.setAttribute('aria-label','Upload schematic');content.append(input);input.onchange=guard(async()=>{const f=input.files[0];if(!f)return;const asset=await api('/api/assets',{method:'POST',headers:{'Content-Type':f.type,'X-PMC-Request':'local-console','X-File-Name':encodeURIComponent(f.name)},body:f});change(()=>{d.schematic_intent??={assets:[],components:[]};if(!d.schematic_intent.assets.some(a=>a.sha256===asset.sha256))d.schematic_intent.assets.push(asset);});schematic();});
    if(intent){action(content,'Remove all schematic intent',()=>{change(()=>d.schematic_intent=null);schematic();});for(const a of intent.assets){const card=element('div',null,'library-card');card.append(element('h3',a.name));const link=element('a','Open local asset');link.href='/api/assets/'+a.sha256;link.target='_blank';link.rel='noopener';card.append(link);content.append(card);}
      const components=element('section');components.append(element('h3','Schematic components'));content.append(components);for(const c of intent.components){const row=element('div',null,'library-card');row.append(element('strong',c.id+' · '+(c.function||'Schematic component')));field(row,'Placement · '+c.id,c.placement_id||'',v=>change(()=>{c.placement_id=v||null;c.cavity_id=v?(d.features.find(f=>f.id===v)?.cavity_id||null):null;}),{'':'Not implemented',...Object.fromEntries(d.features.filter(f=>f.kind==='cavity').map(f=>[f.id,f.id]))});components.append(row);}
      action(components,'Add schematic component',()=>{change(()=>{let i=1;while(intent.components.some(c=>c.id==='COMP'+i))i++;intent.components.push({id:'COMP'+i,label:'Component '+i,function:'',cartridge_id:null,cavity_id:null,interface_nets:{},placement_id:null});});schematic();});
    }
    action(content,'Analyze schematics with AI Design',()=>ai.open());
  }
  const ai=aiDesign(ctx,open);$('schematic-open').onclick=schematic;
  const placedDefinition=feature=>get().library.find(d=>d.id===feature.cavity_id);
  return {
    viewDefinition(feature){const definition=placedDefinition(feature);if(!definition)return notice('Cavity definition is unavailable in this project session.',true);library.viewDefinition(definition,{interfaceNames:Object.fromEntries(definition.zones.map((zone,index)=>[zone.id,displayInterfaceName(get(),feature.id,zone.id,{index})]))});},
    duplicateDefinition(feature){const definition=placedDefinition(feature);if(!definition)return notice('Cavity definition is unavailable in this project session.',true);library.duplicateAsCustom(definition);},
    replaceFromLibrary(feature){library({title:'Replace '+feature.id+' from Engineering Library',actionLabel:'Use as Replacement',onSelect:definition=>{remember(definition);dialog.close();replaceCavity(feature,definition.id);}});}
  };
}
