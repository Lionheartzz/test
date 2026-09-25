import {aiDesign} from './ai-design.js';
import {isCavity} from './definition-role.js';
import {customPort,portSetup} from './port-setup.js';
import {guided} from './guided.js';
import {libraryUI} from './library-ui.js';
import {projectUI} from './project-ui.js';
import {clamp,syncNets,featureLabel,returnNetToAutomatic} from './kinematics.js';
import {hydrateDesign} from './domain.js';
import {displayMemberName,displayNetName,displayInterfaceName} from './presentation.js';

function flowSizing(net,tools,requiredDepth,unit){
  if(!net.flow_lpm)return {required:null,selected:null};
  const area=net.flow_lpm*1000/60/(net.velocity_limit||6),required=Math.sqrt(4*area/Math.PI);
  const selected=[...(tools||[])].filter(row=>row.max_depth_mm>=requiredDepth&&Math.PI*row.diameter_mm*row.diameter_mm/4+1e-9>=area).sort((a,b)=>a.diameter_mm-b.diameter_mm||(a.unit_system===unit?-1:1)-(b.unit_system===unit?-1:1)||a.max_depth_mm-b.max_depth_mm||a.id.localeCompare(b.id))[0];
  return {required,selected:selected?.diameter_mm||null,tool:selected||null};
}

const schematicInterfacePattern=/^[A-Za-z][A-Za-z0-9_-]{0,39}$/;

export function filterThreadChoices(threads,family,native='',search=''){
  const tokens=String(search).toLowerCase().split(/\s+/).filter(Boolean);
  return threads.filter(row=>row.normalized_family===family&&(!native||row.unit_system===native)&&tokens.every(token=>(row.display_name+' '+row.nominal_size+' '+row.pitch_tpi+' '+row.thread_class).toLowerCase().includes(token)));
}

export function renameExpectedInterface(component,previous,next){
  const value=String(next||'').trim();
  if(!schematicInterfacePattern.test(value))throw Error('Expected interface ID must start with a letter and use only letters, numbers, _ or -.');
  if(component.expected_interfaces.some(id=>id===value&&id!==previous))throw Error('Expected interface ID must be unique.');
  const index=component.expected_interfaces.indexOf(previous);
  if(index<0)throw Error('Expected interface no longer exists.');
  component.expected_interfaces[index]=value;component.interface_nets??={};
  if(Object.hasOwn(component.interface_nets,previous)){component.interface_nets[value]=component.interface_nets[previous];delete component.interface_nets[previous];}
  component.interface_dispositions??={};if(Object.hasOwn(component.interface_dispositions,previous)){component.interface_dispositions[value]=component.interface_dispositions[previous];delete component.interface_dispositions[previous];}
}

export function nextExpectedInterface(component,placement){
  const actual=Object.keys(placement?.interface_nets||{}),unused=actual.find(id=>!component.expected_interfaces.includes(id));
  if(unused)return unused;
  if(actual.length)return null;
  let i=1;while(component.expected_interfaces.includes('port'+i))i++;
  return 'port'+i;
}

export function workflows(ctx){
  const {adoptRoute,replaceCavity,$,element,field,action,api,post,get,state,change,set,newId,select,notice,resolved}=ctx;
  const content=$('workflow-content'),dialog=$('workflow-dialog');
  const guard=fn=>async()=>{try{await fn();$('workflow-error').textContent='';}catch(e){$('workflow-error').textContent=e.message;}};
  function open(title){$('workflow-title').textContent=title;content.replaceChildren();$('workflow-error').textContent='';if(!dialog.open)dialog.showModal();}
  $('workflow-close').onclick=()=>dialog.close();
  let routingTools=[];api('/api/tools?type=drill').then(result=>routingTools=result.items||[]).catch(()=>{});
  const definitions=()=>Object.fromEntries((get().library||[]).map(d=>[d.id,d]));
  const threadDefinitions=()=>Object.fromEntries((get().threads||[]).map(row=>[row.id,row]));
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
    for(const z of def.zones)field(content,'Interface '+z.id+' → Net',mapping[z.id],v=>mapping[z.id]=v,Object.fromEntries(get().nets.map(n=>[n.id,n.label||n.id])));
    action(content,'Add cavities to draft',()=>{if(!Number.isInteger(quantity)||quantity<1||quantity>20){$('workflow-error').textContent='Quantity must be 1–20.';return;}for(let i=0;i<quantity;i++)insertNow(def,face,{...mapping},i);});
  }

  const library=libraryUI(ctx,{open,insert,onCustomSaved:remember});
  ctx.externalPortLibrary=library.externalPorts;ctx.createCustomExternalPort=library.createExternalPort;ctx.viewExternalPort=library.viewExternalPort;
  projectUI({...ctx,openSchematic:schematic});
  guided(ctx,open,library,nets);
  $('library-open').onclick=guard(library);

  $('add-mounting').onclick=guard(async()=>{
    const response=await api('/api/threads?usable_only=true&limit=500'),threads=response.items;
    const preferred=get()?.project_context==='inch'?'UNC':'Metric';let mode='plain',face='top',diameter=12,depth=20,threadDepth=16,threadId='',threadFamily=response.families.includes(preferred)?preferred:response.families[0]||'',nativeUnit='',threadSearch='',through=false;
    const render=()=>{open('Add mounting hole');field(content,'Hole type',mode,v=>{mode=v;render();},{plain:'Plain Hole',threaded:'Threaded Hole'});field(content,'Face',face,v=>face=v,{top:'Top',bottom:'Bottom',front:'Front',back:'Back',left:'Left',right:'Right'});
    if(mode==='plain')field(content,'Diameter / mm',diameter,v=>diameter=v,null,true);else{field(content,'Thread standard / family',threadFamily,v=>{threadFamily=v;threadId='';render();},Object.fromEntries(response.families.map(value=>[value,value])));field(content,'Native standard',nativeUnit,v=>{nativeUnit=v;threadId='';render();},{'':'All',metric:'Metric-native',inch:'Inch-native'});field(content,'Search thread size / specification',threadSearch,v=>{threadSearch=v;threadId='';render();});const visible=filterThreadChoices(threads,threadFamily,nativeUnit,threadSearch);if(!visible.some(row=>row.id===threadId))threadId=visible[0]?.id||'';field(content,'Thread size / specification',threadId,v=>threadId=v,Object.fromEntries(visible.map(row=>[row.id,`${row.display_name} · tap Ø${Number(row.tap_diameter_mm).toFixed(3)} mm · ${row.unit_system} native`])));field(content,'Thread depth / mm',threadDepth,v=>threadDepth=v,null,true);}
    field(content,'Blind drill depth / mm',depth,v=>depth=v,null,true);field(content,'Hole termination',String(through),v=>through=v==='true',{false:'Blind',true:'Through block'});
    content.append(element('p',mode==='plain'?'Creates an explicit non-hydraulic plain bore.':'Thread identity and tap diameter come from SQLite. Exact CAD uses the manufacturing bore envelope, without helical thread faces.'));
    action(content,'Add mounting hole',guard(async()=>{const baseline=JSON.stringify(get()),d=structuredClone(get()),dims=[d.block.length,d.block.width,d.block.height],axes={top:[0,1,2],bottom:[0,1,2],front:[0,2,1],back:[0,2,1],left:[1,2,0],right:[1,2,0]}[face],id='MNT_'+crypto.randomUUID().replaceAll('-','');
      const finalDepth=through?dims[axes[2]]:depth;if(mode==='threaded'&&!threadId)throw Error('Select a source-backed thread definition.');
      d.features.push({id,kind:'mounting',face,u:dims[axes[0]]/2,v:dims[axes[1]]/2,diameter:mode==='plain'?diameter:null,depth:finalDepth,through,tip_angle:through?180:118,mounting_mode:mode,thread_definition_id:mode==='threaded'?threadId:null,thread_depth:mode==='threaded'?(through?finalDepth:threadDepth):null});
      const checked=await post('/api/check-design',d);if(JSON.stringify(get())!==baseline)throw Error('Draft changed while adding mounting hole. Retry.');if(change(()=>set(hydrateDesign(checked,definitions(),Object.fromEntries([...get().threads,...threads].map(row=>[row.id,row])))))){select(id);dialog.close();notice('Mounting hole added. Position it and Validate before drawing.');}
    }));
    };render();
  });

  $('add-engraving').onclick=()=>{
    let face='top',u=get().block.length/2,v=get().block.width/2,text='P',rotation=0,textHeight=5,depth=.3;
    open('Add production engraving');field(content,'Face',face,value=>face=value,{top:'Top',bottom:'Bottom',front:'Front',back:'Back',left:'Left',right:'Right'});
    field(content,'Position U / mm',u,value=>u=value,null,true);field(content,'Position V / mm',v,value=>v=value,null,true);field(content,'Text',text,value=>text=value);
    field(content,'Rotation / degrees',rotation,value=>rotation=value,null,true);field(content,'Text height / mm',textHeight,value=>textHeight=value,null,true);field(content,'Machining depth / mm',depth,value=>depth=value,null,true);
    content.append(element('p','Engraving is exact shallow stock removal and Drawing/manufacturing identity. It never joins a Hydraulic Net.'));
    action(content,'Add engraving',guard(async()=>{const baseline=JSON.stringify(get()),d=structuredClone(get()),id='ENG_'+crypto.randomUUID().replaceAll('-','');d.engravings??=[];d.engravings.push({id,face,u,v,text,rotation,text_height:textHeight,depth});const checked=await post('/api/check-design',d);if(JSON.stringify(get())!==baseline)throw Error('Draft changed while adding engraving. Retry.');if(change(()=>set(hydrateDesign(checked,definitions(),threadDefinitions()))))dialog.close();}));
  };

  $('add-block-modifier').onclick=()=>{
    let kind='rectangular-cutout',face='top',u=get().block.length/2,v=get().block.width/2,width=20,height=10,depth=5,rotation=0,size=2;
    const render=()=>{open('Add limited block machining');field(content,'Operation',kind,value=>{kind=value;render();},{'rectangular-cutout':'Rectangular cutout',chamfer:'Chamfer selected face edges'});field(content,'Face',face,value=>face=value,{top:'Top',bottom:'Bottom',front:'Front',back:'Back',left:'Left',right:'Right'});
      if(kind==='rectangular-cutout'){field(content,'Center U / mm',u,value=>u=value,null,true);field(content,'Center V / mm',v,value=>v=value,null,true);field(content,'Width / mm',width,value=>width=value,null,true);field(content,'Height / mm',height,value=>height=value,null,true);field(content,'Depth / mm',depth,value=>depth=value,null,true);field(content,'Rotation / degrees',rotation,value=>rotation=value,null,true);}else field(content,'Chamfer size / mm',size,value=>size=value,null,true);
      content.append(element('p','This is an explicit exact manufacturing operation. Freeform solid modeling is intentionally unavailable.'));
      action(content,'Add block machining',guard(async()=>{const baseline=JSON.stringify(get()),d=structuredClone(get()),id='BLK_'+crypto.randomUUID().replaceAll('-','');d.block_modifiers??=[];d.block_modifiers.push(kind==='chamfer'?{id,kind,face,size}:{id,kind,face,u,v,width,height,depth,rotation});const checked=await post('/api/check-design',d);if(JSON.stringify(get())!==baseline)throw Error('Draft changed while adding block machining. Retry.');if(change(()=>set(hydrateDesign(checked,definitions(),threadDefinitions()))))dialog.close();}));
    };render();
  };

  $('add-port').onclick=()=>{
    const p=customPort();let net=get().nets[0]?.id||'P';
    const render=()=>{open('Add external port');field(content,'Hydraulic net',net,v=>{net=v;render();},Object.fromEntries(get().nets.map(n=>[n.id,n.label||n.id])));portSetup(ctx,content,p,net,render);
      action(content,'Add port to draft',guard(async()=>{if(p.mode!=='oneoff'&&!p.definition)throw Error('Select a machining definition first.');const baseline=JSON.stringify(get()),d=structuredClone(get()),id='PORT_'+crypto.randomUUID().replaceAll('-','');
        const f={id,kind:'port',face:p.face,u:0,v:0,circuit:net,diameter:p.diameter,depth:p.depth,clearance_diameter:p.clearance,size:p.size.slice(0,80),port_type:p.definition?p.definition.label:'Custom straight bore'};
        if(p.definition){remember(p.definition);f.port_definition_id=p.definition.id;f.diameter=Math.min(...p.definition.stages.map(x=>x.diameter));f.depth=p.definition.zones[0].end;f.clearance_diameter=p.definition.clearance_diameter;f.clearance_height=p.definition.clearance_height;f.tip_angle=180;}
        const axes={top:['length','width'],bottom:['length','width'],left:['width','height'],right:['width','height'],front:['length','height'],back:['length','height']}[p.face];[f.u,f.v]=clamp(f,get(),get().block[axes[0]]/2,get().block[axes[1]]/2);d.features.push(f);if(!p.definition){let n=1;while(d.review_items.some(item=>item.id==='PORT_SPEC_'+n))n++;d.review_items.push({id:'PORT_SPEC_'+n,kind:'component',subject:id,description:'Resolve thread/fitting installation and machining specification for this one-off custom straight bore.',status:'open'});}syncNets(d);
        const checked=await post('/api/check-design',d);if(JSON.stringify(get())!==baseline)throw Error('Draft changed while preparing the port. Retry.');if(change(()=>set(hydrateDesign(checked,definitions(),Object.fromEntries((get().threads||[]).map(row=>[row.id,row])))))){select(id);dialog.close();notice('External port added. Review position and fitting installation.');}
      }));
    };render();
  };

  function netMembers(d,netId){const members=[];for(const f of d.features){if(f.suppressed)continue;if(f.kind==='cavity'){for(const [id,net]of Object.entries(f.interface_nets||{}))if(net===netId)members.push(f.id+':'+id);}else if(f.kind==='port'&&f.circuit===netId)members.push(f.id);}return members;}
  function nets(){
    open('Hydraulic Nets · intent and derived connections');content.append(element('p','Net members are derived from cavity interface assignments and external ports. Automatic routing proposes geometry; exact validation decides whether it is acceptable.'));
    action(content,'Optimize routes with exact checks',guard(async()=>{if(!state().project_id)throw Error('Save Project before running exact route optimization.');const baseline=JSON.stringify(get());const r=await post('/api/optimize-routes',{design:get(),project_id:state().project_id,expected_revision:state().revision,max_attempts:6});if(JSON.stringify(get())!==baseline)throw Error('Draft changed during optimization.');change(()=>set(hydrateDesign(r.design,definitions(),Object.fromEntries((get().threads||[]).map(row=>[row.id,row])))));nets();content.prepend(element('p',`${r.attempts.length} exact candidates · FAIL ${r.baseline.FAIL} → ${r.final.FAIL}. Validate to commit.`));}));
    const advanced=element('details');advanced.append(element('summary','Advanced'));content.append(advanced);action(advanced,'Reset all routes to automatic',()=>{if(!confirm('This will remove manual/frozen routing geometry and return all hydraulic nets to automatic routing. Continue?'))return;change(()=>{for(const net of get().nets)returnNetToAutomatic(get(),net.id);});nets();});
    const newNet=element('div',null,'action-row'),name=element('input');name.setAttribute('aria-label','New net ID');name.placeholder='NET_P';newNet.append(name);action(newNet,'Add net',()=>{if(!/^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(name.value)||get().nets.some(n=>n.id===name.value)){$('workflow-error').textContent='Use a unique engineering ID';return;}change(()=>get().nets.push({id:name.value,label:name.value,routing:'automatic',diameter:8}));nets();});content.append(newNet);
    for(const n of get().nets){const card=element('section',null,'library-card'),members=netMembers(get(),n.id);content.append(card);card.append(element('h3',n.label||n.id),element('p',members.map(member=>displayMemberName(get(),member)).join(' ↔ ')||'No interfaces assigned'));const edit=(label,value,fn,o=null,num=false)=>field(card,label,value,v=>{if(change(()=>fn(v)))nets();},o,num);
      edit('Net label · '+n.id,n.label||n.id,v=>n.label=v);
      const colorWrap=element('label','Display color · '+n.id,'field'),color=element('input');color.type='color';color.setAttribute('aria-label','Display color · '+n.id);color.value=n.color||'#b08bea';color.onchange=()=>{if(change(()=>n.color=color.value))nets();};colorWrap.append(color);card.append(colorWrap);
      edit('Diameter sizing · '+n.id,n.diameter_mode||'automatic',v=>{n.diameter_mode=v;n.routing_variant=null;},{automatic:'Automatic from flow',manual:'Engineer override'});
      const sizing=flowSizing(n,routingTools,0,get().project_context);
      if(n.diameter_mode==='automatic'){
        card.append(element('p',sizing.required==null?'Enter flow to calculate the required passage diameter.':`Calculated minimum: ${sizing.required.toFixed(2)} mm · ${sizing.selected?`Selected standard drill: Ø${sizing.selected.toFixed(2)} mm`:'No available standard drill is large enough.'}`,'property-note'));
        const effective=field(card,'Effective drill diameter · '+n.id,sizing.selected==null?'Unresolved':sizing.selected.toFixed(2),()=>{});effective.disabled=true;
      }else edit('Engineer override drill diameter · '+n.id,n.diameter,v=>{n.diameter=v;n.routing_variant=null;},null,true);
      edit('Velocity limit m/s · '+n.id,n.velocity_limit||6,v=>{n.velocity_limit=v;n.routing_variant=null;},null,true);edit('Drilling mode · '+n.id,n.drilling_mode||'orthogonal',v=>{n.drilling_mode=v;n.routing_variant=null;},{orthogonal:'Orthogonal only','allow-angled':'Allow angled proposals',simplest:'Prefer simplest manufacturable proposal'});edit('First routing axis · '+n.id,n.preferred_axis||'auto',v=>{n.preferred_axis=v;n.routing_variant=null;},{auto:'Compare all axes',x:'X',y:'Y',z:'Z'});edit('Entry preference · '+n.id,n.entry_preference||'nearest',v=>{n.entry_preference=v;n.routing_variant=null;},{nearest:'Nearest / reuse port',negative:'Negative face',positive:'Positive face'});edit('Flow L/min · '+n.id,n.flow_lpm,v=>{n.flow_lpm=v||null;n.routing_variant=null;},null,'optional');edit('Pressure bar · '+n.id,n.pressure_bar,v=>n.pressure_bar=v||null,null,'optional');
      if(n.routing==='automatic')action(card,'Refine / Freeze '+displayNetName(get(),n.id)+' for manual editing',guard(async()=>{if(await adoptRoute(n.id))nets();else throw Error($('notice').textContent);}));
      else action(card,'Return '+displayNetName(get(),n.id)+' to automatic routing',()=>{change(()=>returnNetToAutomatic(get(),n.id));nets();});
    }
    const route=resolved();if(route){const details=element('details');details.append(element('summary','Inspect generated drilling coordinates'));for(const f of route.features.filter(f=>f.route_net)){const row=element('div',null,'port-row');row.append(element('p',`${featureLabel(f,route)} · ${displayNetName(route,f.route_net)} · ${f.face} U${f.u.toFixed(2)} V${f.v.toFixed(2)} · Ø${f.diameter} × ${f.depth.toFixed(2)}`));action(row,'Refine / Edit in 3D',guard(async()=>{if(await adoptRoute(f.route_net,f.id))dialog.close();else throw Error($('notice').textContent);}));details.append(row);}content.append(details);}
  }
  $('nets-open').onclick=nets;

  function schematic(){
    open('Schematic Intent');const d=get(),intent=d.schematic_intent;
    content.append(element('p',intent?'Schematic conformance applies because this project contains explicit intent.':'This project has no schematic intent. Cavity placement alone does not create schematic components or conformance requirements.'));
    if(!intent)action(content,'Create manual schematic intent',()=>{change(()=>d.schematic_intent={assets:[],components:[]});schematic();});
    const input=element('input');input.type='file';input.accept='.pdf,.png,.jpg,.jpeg';input.setAttribute('aria-label','Upload schematic');content.append(input);input.onchange=guard(async()=>{const f=input.files[0];if(!f)return;const asset=await api('/api/assets',{method:'POST',headers:{'Content-Type':f.type,'X-PMC-Request':'local-console','X-File-Name':encodeURIComponent(f.name)},body:f});change(()=>{d.schematic_intent??={assets:[],components:[]};if(!d.schematic_intent.assets.some(a=>a.sha256===asset.sha256))d.schematic_intent.assets.push(asset);});schematic();});
    if(intent){action(content,'Remove all schematic intent',()=>{change(()=>d.schematic_intent=null);schematic();});for(const a of intent.assets){const card=element('div',null,'library-card');card.append(element('h3',a.name));const link=element('a','Open local asset');link.href='/api/assets/'+a.sha256;link.target='_blank';link.rel='noopener';card.append(link);content.append(card);}
      const components=element('section');components.append(element('h3','Schematic components'));content.append(components);for(const c of intent.components){
        c.expected_interfaces??=Object.keys(c.interface_nets||{});c.interface_dispositions??=Object.fromEntries(c.expected_interfaces.map(id=>[id,Object.hasOwn(c.interface_nets||{},id)?'connected':'unknown']));const row=element('div',null,'library-card');row.append(element('strong',c.id));const rerender=fn=>{if(change(fn))schematic();};
        field(row,'Label · '+c.id,c.label||'',v=>rerender(()=>c.label=v));field(row,'Function · '+c.id,c.function||'',v=>rerender(()=>c.function=v));
        field(row,'Implemented by placement · '+c.id,c.placement_id||'',v=>rerender(()=>{const placement=d.features.find(f=>f.id===v);c.placement_id=v||null;c.cavity_id=placement?.cavity_id||null;c.cartridge_id=placement?.cartridge_id||null;}),{'':'Not implemented',...Object.fromEntries(d.features.filter(f=>f.kind==='cavity').map(f=>[f.id,featureLabel(f,d)]))});
        const placement=d.features.find(f=>f.kind==='cavity'&&f.id===c.placement_id),actualInterfaces=Object.keys(placement?.interface_nets||{});
        row.append(element('p',c.placement_id?`Explicit binding: cavity ${c.cavity_id||'unset'} · cartridge ${c.cartridge_id||'none'}`:'No placement binding.','property-note'));
        for(const port of c.expected_interfaces){const portRow=element('div',null,'port-row'),interfaceOptions=actualInterfaces.length?{'':'Select cavity interface',...Object.fromEntries(actualInterfaces.map(id=>[id,id]))}:null;
          field(portRow,'Expected interface ID · '+c.id,port,v=>{try{rerender(()=>renameExpectedInterface(c,port,v));}catch(error){$('workflow-error').textContent=error.message;}},interfaceOptions);
          field(portRow,port+' disposition',c.interface_dispositions[port]||'unknown',v=>rerender(()=>{c.interface_dispositions[port]=v;if(v!=='connected')delete c.interface_nets[port];}),{connected:'Connected',blocked:'Blocked',terminated:'Terminated',unknown:'Unknown / review'});
          if(c.interface_dispositions[port]==='connected')field(portRow,port+' → Hydraulic Net',c.interface_nets?.[port]||'',v=>rerender(()=>{c.interface_nets??={};if(v)c.interface_nets[port]=v;else delete c.interface_nets[port];}),{'':'Unmapped',...Object.fromEntries(d.nets.map(n=>[n.id,n.label||n.id]))});
          action(portRow,'Remove expected interface',()=>rerender(()=>{c.expected_interfaces=c.expected_interfaces.filter(id=>id!==port);delete c.interface_nets[port];delete c.interface_dispositions[port];}));row.append(portRow);
        }
        action(row,'Add expected interface',()=>{const id=nextExpectedInterface(c,placement);if(!id){$('workflow-error').textContent='All interfaces on the bound cavity are already expected.';return;}rerender(()=>{c.expected_interfaces.push(id);c.interface_dispositions[id]='unknown';});});
        action(row,c.placement_id?'Unbind placement':'Remove component',()=>rerender(()=>{if(c.placement_id){c.placement_id=null;c.cavity_id=null;c.cartridge_id=null;}else intent.components=intent.components.filter(item=>item.id!==c.id);}));if(c.placement_id)action(row,'Remove component',()=>rerender(()=>intent.components=intent.components.filter(item=>item.id!==c.id)));components.append(row);
      }
      action(components,'Add schematic component',()=>{change(()=>{let i=1;while(intent.components.some(c=>c.id==='COMP'+i))i++;intent.components.push({id:'COMP'+i,label:'Component '+i,function:'',cartridge_id:null,cavity_id:null,expected_interfaces:[],interface_nets:{},interface_dispositions:{},placement_id:null});});schematic();});
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
