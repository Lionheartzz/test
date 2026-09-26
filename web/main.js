import {createPreviewQueue} from './preview-queue.js';
import {streamExactPreview} from './preview-stream.js';
import {isCavity} from './definition-role.js';
import './ui-tokens.css';
import './style.css';
import {createViewer} from './viewer.js';
import {clamp,syncNets,featureLabel,returnNetToAutomatic} from './kinematics.js';
import {pose,axes} from './kinematics.js';
import {workflows} from './workflows.js';
import {projectLibrary} from './project-library.js';
import {hydrateDesign,cloneDesign} from './domain.js';
import {displayIdentity,displayRuleName,displayInterfaceName,displayNetName} from './presentation.js';
import {createStudioShell} from './studio-shell.js';
import {createViewCube} from './viewcube.js';
import {reportSource,resolveCheckTargets,issueReferences} from './validation-view.js';
import './studio.css';
const $=id=>document.getElementById(id),colors={P:'#ef5959',T:'#459cff',A:'#41ca8b',B:'#f2d454'},faces=Object.fromEntries(['top','bottom','front','back','left','right'].map(f=>[f,f]));
let draftCheckedSignature=null,reportWasDraft=false,projectEpoch=0,savePending=null,statusPollPending=false;
let viewMode='review',lastUsablePreview=null,displayedDraftSignature=null,displayedSource='none';
let state,draft,report,reportDesign,model,resolved,selection='block',dirty=false,busy=false,externalChange=false,viewer,viewCube,history=[],future=[],dragStart,exactPreview=null;
const currentDisplayedDesign=()=>viewer?.displayDesign()||draft;
function markDisplayed(snapshot,source){displayedDraftSignature=JSON.stringify(snapshot);displayedSource=source;}
let materialCatalog=[];
let modifierCatalog=[];
const shell=createStudioShell({$});
const previewDiagnostics=[];globalThis.__PMC_PREVIEW_TIMINGS=previewDiagnostics;
function previewTiming(value){const row=Object.fromEntries(Object.entries(value).map(([k,v])=>[k,typeof v==='number'?Math.round(v*100)/100:v]));previewDiagnostics.push(row);if(previewDiagnostics.length>24)previewDiagnostics.shift();}
function element(tag,text,cls){const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;}
function notice(message,error=false){$('notice').textContent=message;$('notice').className=error?'error':'';}
async function api(url,options={}){
  const limit=['/api/build','/api/optimize-routes'].includes(url)?330000:url==='/api/refine-route'?65000:url==='/api/freeze-net'?35000:30000;
  try{
    const r=await fetch(url,{signal:AbortSignal.timeout(limit),...options});
    if(!r.ok){const b=await r.json().catch(()=>({}));throw Error(typeof b.detail==='string'?b.detail:Array.isArray(b.detail)?b.detail.map(e=>`${(e.loc||[]).filter(x=>x!=='body').join('.')}: ${e.msg}`).join('; '):JSON.stringify(b.detail||r.status));}
    return await r.json();
  }catch(error){if(error.name==='TimeoutError')throw Error('Request timed out. Draft and last usable view retained. Refresh project status before retrying a save or build.');throw error;}
}
const post=(url,body,options={})=>api(url,{...options,method:'POST',headers:{'Content-Type':'application/json','X-PMC-Request':'local-console',...options.headers},body:JSON.stringify(body)});
api('/api/materials').then(result=>materialCatalog=result.items||[]).catch(()=>{});
api('/api/machining-modifiers').then(result=>modifierCatalog=result.items||[]).catch(()=>{});
function change(fn){if(busy)return false;const before=cloneDesign(draft);try{fn();syncNets(draft);history.push(before);if(history.length>40)history.shift();future=[];markDirty();return true;}catch(e){draft=before;notice(e.message,true);select(selection);return false;}}
const solidOverlay=element('div',null,'viewport-loading');solidOverlay.setAttribute('role','status');solidOverlay.hidden=true;$('viewport').append(solidOverlay);
function solidStatus(text=''){solidOverlay.hidden=!text;solidOverlay.textContent=text;}
function previewState(kind,text){$('viewport').dataset.previewState=kind;$('model-info').textContent=text;}
function showSolid(result,snapshot=draft,context=null){solidStatus();resolved=hydrateDesign({...snapshot,features:result.features},draft.library,draft.threads);viewer?.setReferences(result.features);viewer?.load(result.model,resolved);markDisplayed(snapshot,'proposal');viewer?.setDesign(draft);exactPreview=context&&result.model.deferred_layers?.length?{...context,designRevision:result.design_revision,pending:new Set()}:null;lastUsablePreview={model:result.model,design:resolved,draftSignature:displayedDraftSignature};renderTree();select(selection);renderReport();previewState('exact-proposal','EXACT BREP · CURRENT PROPOSAL · NOT VALIDATED / NOT OPTIMIZED'+(result.model.brep_valid===false?' · BREP TOPOLOGY INVALID':''));notice(result.model.brep_valid===false?'Exact preview ready. Current proposal has invalid BRep topology; Validate reports engineering failures.':'Exact preview ready. Current proposal is not validated or optimized.');requestLayer(viewMode);}
const previews=createPreviewQueue({post,stream:streamExactPreview,
  cancelRemote:(owner,version)=>post('/api/preview-cancel',{owner,version},{signal:AbortSignal.timeout(2000)}),
  onFast(p,snapshot){exactPreview=null;resolved=hydrateDesign(p.design,draft.library,draft.threads);viewer?.preview(resolved);markDisplayed(snapshot,'proposal');viewer?.setReferences(resolved.features);viewer?.setDesign(draft);lastUsablePreview={design:resolved,draftSignature:displayedDraftSignature};renderTree();select(selection);renderReport();previewState('approximate','APPROXIMATE LIVE VIEW · CURRENT PROPOSAL · NOT VALIDATED');},
  onExact:showSolid,
  onTiming:previewTiming,
  onStatus(status){solidStatus(status==='exact'?'Computing exact current proposal… Not validated or optimized.':'');if(status==='exact')previewState('computing','APPROXIMATE LIVE VIEW · EXACT BREP COMPUTING · NOT VALIDATED');},
  onError(error){exactPreview=null;if(lastUsablePreview){const p=lastUsablePreview;if(p.model)viewer?.load(p.model,p.design);else viewer?.preview(p.design);displayedDraftSignature=p.draftSignature;displayedSource='retained';viewer?.setDesign(p.design);renderTree();select(selection);renderReport();}solidStatus();previewState('unavailable','EXACT PREVIEW UNAVAILABLE · PREVIEW FAILED · LAST USABLE VIEW RETAINED · '+(lastUsablePreview?.model?'EXACT':'APPROXIMATE')+' · '+error.message);notice('Preview: '+error.message,true);}
});
async function requestLayer(mode){
  const layer=mode==='void'?'void':mode==='features'?'features':null,token=exactPreview;
  if(!layer||!viewer?.needsLayer(layer))return true;
  if(!token)return false;
  token.layerPromises??=new Map();
  if(token.layerPromises.has(layer))return token.layerPromises.get(layer);
  const started=performance.now();token.pending.add(layer);
  const promise=(async()=>{
    try{const result=await post('/api/preview-layer',{design_revision:token.designRevision,layer},{headers:{'X-PMC-Preview-Owner':token.owner,'X-PMC-Preview-Version':String(token.version)}});if(exactPreview!==token||result.design_revision!==token.designRevision||result.layer!==layer)return false;viewer.loadLayer(layer,result.parts);previewTiming({kind:'lazy-layer-request',layer,total_ms:performance.now()-started});return true;}
    catch(error){if(exactPreview===token)notice('Exact inspection layer unavailable: '+error.message,true);return false;}
    finally{token.pending.delete(layer);token.layerPromises.delete(layer);}
  })();token.layerPromises.set(layer,promise);return promise;
}
function requestSolid(){
  if(!draft||dragStart||busy)return;
  if(!dirty&&!state?.stale&&state?.build){exactPreview=null;previews.cancel();if(model){viewer?.load(model,resolved);lastUsablePreview={model,design:resolved,draftSignature:JSON.stringify(draft)};}else{viewer?.preview(resolved);lastUsablePreview={design:resolved,draftSignature:JSON.stringify(draft)};}markDisplayed(draft,'authoritative');viewer?.setDesign(draft);previewState('authoritative','AUTHORITATIVE VALIDATION · '+state.build.status+' · '+(model?'EXACT MACHINED BREP':'EXACT REVIEW UNAVAILABLE · APPROXIMATE VIEW'));return;}
  previews.schedule(draft,String(projectEpoch));
}
function refreshPreview(){
  solidStatus();
  try{viewer?.preview(draft);markDisplayed(draft,'draft');viewer?.setReferences(draft.features);viewer?.setDesign(draft);previewState('approximate','APPROXIMATE LIVE VIEW · NOT VALIDATED');}
  catch(error){displayedSource='retained';$('model-info').textContent='LAST USABLE VIEW RETAINED · '+error.message;}
  renderTree();select(selection);renderReport();
  if(dragStart)previews.cancel();else requestSolid();
}
function markDirty(){draftCheckedSignature=null;dirty=true;exactPreview=null;viewer?.setIssueMarkers([]);renderHeader();refreshPreview();notice('Draft preview updated. Validate runs exact geometry checks and writes an immutable build.');}
try{viewer=createViewer($('viewport'),select,(id,u,v,done)=>{if(busy||displayedSource==='retained'&&displayedDraftSignature!==JSON.stringify(draft))return;const f=draft.features.find(f=>f.id===id);if(!f)return;const starting=!dragStart;if(starting){dragStart=cloneDesign(draft);previews.cancel();exactPreview=null;draftCheckedSignature=null;viewer?.setIssueMarkers([]);dirty=true;renderHeader();}f.u=u;f.v=v;$('selection-label').textContent=`${featureLabel(f,draft)} · ${f.face} · U ${u.toFixed(1)} / V ${v.toFixed(1)} mm`;notice('Live position · envelope clamped to face · 1 mm snap · preview is not validated');if(!done){viewer?.updateFeature(draft,id);markDisplayed(draft,'draft');if(starting){renderTree();renderReport();}previewState('approximate','APPROXIMATE LOCAL DRAG · NOT VALIDATED');return;}const baseline=dragStart;history.push(baseline);future=[];dragStart=null;select(id);if(f.frozen_net)refineAfterDrag(baseline,id,u,v);else refreshPreview();},{onHover:id=>{for(const row of document.querySelectorAll('#feature-tree [data-feature]'))row.classList.toggle('hovered',row.dataset.feature===id);},onViewChange:()=>viewCube?.sync(),onMarkerSelect:id=>{select(id);viewer?.focus(id);}});$('viewport').addEventListener('pmc-viewer-timing',event=>previewTiming(event.detail));}catch(e){notice('WebGL: '+e.message,true);}

const toolbar=document.querySelector('.viewport-toolbar');
const hudTop=element('div',null,'hud-top');
document.querySelector('.viewport-section').prepend(hudTop);
hudTop.append(toolbar);
if($('viewport').querySelector('.collision-notice'))hudTop.append($('viewport').querySelector('.collision-notice'));
hudTop.append(solidOverlay);
const navigationTools=element('div',null,'navigation-tools');
const projectionButton=action(navigationTools,'Perspective',()=>{
  const next=viewer?.projection()==='perspective'?'orthographic':'perspective';
  if(viewer?.projection(next))projectionButton.textContent=next==='orthographic'?'Orthographic':'Perspective';
});
projectionButton.id='projection-toggle';projectionButton.title='Switch between Perspective and Orthographic';
const focusButton=action(navigationTools,'Focus',()=>{
  const result=viewer?.focus(selection);if(!result?.ok)notice(result?.reason||'Select a visible feature to focus.',true);
});
focusButton.id='focus-selection';focusButton.title='Frame selected object (F)';
const isolateButton=action(navigationTools,'Isolate',async()=>{
  if(busy||!viewer)return;
  if(viewer.inspection().isolation){viewer.clearIsolation();isolateButton.textContent='Isolate';return;}
  if(selection==='block'){notice('Select a displayed feature to isolate.',true);return;}
  const epoch=projectEpoch,target=selection;
  if(viewer.needsLayer('features')){
    notice('Loading owner machining layer for isolation…');
    if(!await requestLayer('features')){notice('Owner machining layer is unavailable in this preview. Full model retained.',true);return;}
    if(epoch!==projectEpoch||target!==selection)return;
  }
  const result=viewer.isolate(target);
  if(result.ok)isolateButton.textContent='Reset isolate';else notice(result.reason,true);
});
isolateButton.id='isolate-selection';
toolbar.insertBefore(navigationTools,$('face-view'));
if(viewer)viewCube=createViewCube($('viewport'),key=>{viewer.setView(key);if($('face-view').querySelector(`option[value="${key}"]`))$('face-view').value=key;},()=>viewer.navigationState());

const clipControls=element('fieldset',null,'clip-controls');
const clipTitle=element('legend','Section / Clipping');clipControls.append(clipTitle);
const clipEnable=element('input');clipEnable.type='checkbox';clipEnable.id='clip-enabled';
const clipAxis=element('select');clipAxis.id='clip-axis';clipAxis.setAttribute('aria-label','Section axis');
for(const axis of ['x','y','z']){const option=element('option',axis.toUpperCase());option.value=axis;clipAxis.append(option);}
const clipKeep=element('select');clipKeep.id='clip-keep';clipKeep.setAttribute('aria-label','Section side to keep');
for(const [value,label]of [['gte','Keep ≥ position'],['lte','Keep ≤ position']]){const option=element('option',label);option.value=value;clipKeep.append(option);}
const clipRange=element('input');clipRange.id='clip-range';clipRange.type='range';clipRange.step='.1';clipRange.min='0';clipRange.value='0';clipRange.setAttribute('aria-label','Section position');
const clipNumber=element('input');clipNumber.id='clip-position';clipNumber.type='number';clipNumber.step='.1';clipNumber.min='0';clipNumber.value='0';clipNumber.setAttribute('aria-label','Section position in millimetres');
const clipReset=action(clipControls,'Reset section',()=>{viewer?.resetClipping();clipEnable.checked=false;clipRange.value='0';clipNumber.value='0';clipNotice.hidden=true;});
clipReset.id='clip-reset';
const clipNotice=element('div',null,'clip-notice');clipNotice.hidden=true;
const clipLabel=element('span');const clipClose=action(clipNotice,'×',()=>clipReset.click());clipClose.setAttribute('aria-label','Close section');clipNotice.prepend(clipLabel);hudTop.append(clipNotice);
for(const node of [Object.assign(element('label','Enable section'),{htmlFor:'clip-enabled'}),clipEnable,clipAxis,clipKeep,clipRange,clipNumber])clipControls.append(node);
clipControls.append(clipReset);
document.querySelector('#display-menu .view-controls').append(clipControls);
const displayedBlock=()=>viewer?.displayBlock()||draft?.block;
function syncClip(){
  if(!viewer||!draft)return;
  const size=displayedBlock()?.[{x:'length',y:'width',z:'height'}[clipAxis.value]]||0;
  clipRange.max=String(size);clipNumber.max=String(size);
  const position=Math.min(size,Math.max(0,Number(clipNumber.value)||0));
  clipNumber.value=String(position);clipRange.value=String(position);
  if(viewer.setClipping({enabled:clipEnable.checked,axis:clipAxis.value,keep:clipKeep.value,position})){
    clipNotice.hidden=!clipEnable.checked;
    clipLabel.textContent=`SECTION ${clipAxis.value.toUpperCase()} ${clipKeep.value==='gte'?'≥':'≤'} ${position.toFixed(1)} mm`;
  }
}
clipEnable.onchange=()=>{if(clipEnable.checked&&!Number(clipNumber.value)){const size=displayedBlock()?.[{x:'length',y:'width',z:'height'}[clipAxis.value]]||0;clipNumber.value=String(size/2);}syncClip();};
clipAxis.onchange=()=>{clipNumber.value=String((displayedBlock()?.[{x:'length',y:'width',z:'height'}[clipAxis.value]]||0)/2);syncClip();};
clipKeep.onchange=syncClip;clipRange.oninput=()=>{clipNumber.value=clipRange.value;syncClip();};clipNumber.onchange=syncClip;

async function refineAfterDrag(baseline,id,u,v){
  const signature=JSON.stringify(draft);notice('Checking adjusted route and connected branches…');
  try{const result=await post('/api/refine-route',{design:baseline,feature_id:id,u,v});if(JSON.stringify(draft)!==signature)return;draft=hydrateDesign(result.design,draft.library,draft.threads);refreshPreview();report=result.report;reportDesign=null;reportWasDraft=true;draftCheckedSignature=JSON.stringify(draft);renderTree();select(id);renderReport();renderHeader();notice(`Draft exact checks: ${report.counts.PASS} PASS / ${report.counts.FAIL} FAIL. ${result.adjusted_branches.length} branches extended. ${result.notes.join(' ')} Validate includes STEP round trip.`,report.status==='FAIL');}
  catch(e){if(JSON.stringify(draft)===signature){refreshPreview();notice('Route remains an unvalidated draft: '+e.message,true);}}
}
let adoptingRoute=false;
async function adoptRoute(netId,id=selection){
  if(adoptingRoute)return false;
  const displayed=currentDisplayedDesign(),proposal=displayed?structuredClone(displayed):null,baseline=JSON.stringify(draft),epoch=projectEpoch;
  const displayedModel=lastUsablePreview?.design===displayed?lastUsablePreview.model:null;
  if(!proposal||displayedDraftSignature!==baseline||displayedSource==='retained'){notice('No current displayed proposal to refine. Wait for the preview.',true);return false;}
  adoptingRoute=true;previews.cancel();solidStatus('Adopting displayed route…');notice('Adopting displayed route… Keeping its geometry.');
  for(const b of document.querySelectorAll('button'))if(b.textContent==='Refine in 3D')b.disabled=true;
  try{
    const result=await post('/api/freeze-net',{design:structuredClone(draft),net:netId,proposal});
    if(projectEpoch!==epoch||JSON.stringify(draft)!==baseline)throw Error('Draft changed during adoption; refresh the preview and retry.');
    if(!change(()=>draft=hydrateDesign(result,draft.library,draft.threads)))throw Error('Could not adopt route while another operation is active.');
    previews.cancel();
    resolved={...proposal,nets:result.nets,features:[...proposal.features.filter(f=>f.route_net!==netId),...result.features.filter(f=>f.frozen_net===netId)]};
    if(displayedModel)viewer?.load(displayedModel,resolved);else viewer?.preview(resolved);
    markDisplayed(draft,'proposal');viewer?.setReferences(resolved.features);viewer?.setDesign(draft);lastUsablePreview={model:displayedModel,design:resolved,draftSignature:displayedDraftSignature};
    $('model-info').textContent=(displayedModel?'EXACT BREP':'CURRENT PROPOSAL')+' · REFINED / MANUAL · NOT VALIDATED';
    renderTree();select(id);notice('Refined / manual route · '+netId+' · Drag the selected drilling to edit. Geometry is unchanged; Validate checks it.');return true;
  }catch(e){notice('Refine failed: '+e.message,true);return false;}
  finally{adoptingRoute=false;solidStatus();for(const b of document.querySelectorAll('button'))if(b.textContent==='Refine in 3D')b.disabled=false;}
}

function renderHeader(){
  if(!draft)return;
  const reviewCount=(draft.review_items||[]).filter(r=>r.status==='open').length
    +(draft.schematic_intent?.components||[]).filter(c=>!c.placement_id).length;
  $('review-open').textContent='Engineering Review · '+reviewCount;
  $('review-count').textContent=String(reviewCount);
  $('review-count').hidden=!reviewCount;
  $('project-name').textContent=draft.name;
  $('project-name').title=draft.name;
  $('dirty-dot').classList.toggle('dirty',dirty);
  $('dirty-dot').setAttribute('aria-label',dirty?'Unsaved draft':'Draft saved');
  $('dirty-dot').title=externalChange?'Project changed on disk; local draft retained.':dirty?'Unsaved draft':'Draft saved';
  const b=draft.block;
  $('dimensions').textContent=`${b.length} × ${b.width} × ${b.height} mm`;
  $('revision').textContent='SHA '+state.revision.slice(0,8);
  const status=dirty?'DRAFT':!state.build?'SAVED DRAFT':externalChange||state.stale?'STALE':state.build.status;
  $('status').textContent=status;
  $('status').className='badge '+(status==='FAIL'?'fail':status==='PASS'?'':'warning');
  const reason=!state.build?'A current build is required for exports.':busy?'Exact build in progress.':externalChange?'Project changed on disk; reload before exporting.':dirty?'Save and Validate this draft before exporting.':state.stale?'Build is stale; Validate to update.':status!=='PASS'?'Production STEP requires a current PASS build.':'Current build available.';
  $('export-reason').textContent=reason;
  for(const [id,name]of [['step-download','production.step'],['engineering-step-download','engineering.step'],['data-download','design.json'],['report-download','validation.md'],['chart-download','drill-chart.csv'],['manufacturing-download','manufacturing.json']]){
    const ok=!!state.build&&!dirty&&!state.stale&&!externalChange&&!busy&&(id!=='step-download'||status==='PASS');
    const link=$(id);
    link.classList.toggle('disabled',!ok);
    link.setAttribute('aria-disabled',String(!ok));
    link.title=ok?'Download from current build':reason;
    if(ok){link.href=`/api/artifacts/${state.build.build_id}/${name}`;link.download=name;}
    else{link.removeAttribute('href');link.removeAttribute('download');}
  }
  $('build').textContent=busy?'Computing exact solids…':'Validate';
  $('undo').disabled=busy||!history.length;
  $('redo').disabled=busy||!future.length;
  if(report){
    const source=reportSource({report,build:state?.build,dirty,stale:state?.stale,externalChange,draftCheckedSignature,draftSignature:JSON.stringify(draft),displayedDraftSignature,displayedSource,reportWasDraft});
    $('check-counts').textContent=`${source.label} · ${report.counts.PASS} PASS / ${report.counts.WARNING} WARNING / ${report.counts.FAIL} FAIL`;
  }else $('check-counts').textContent='Not validated';
}

function renderTree(){
  const tree=$('feature-tree');tree.replaceChildren();
  $('feature-count').textContent=(draft.features.length+(draft.engravings?.length||0)+(draft.block_modifiers?.length||0))+' ITEMS';
  $('feature-count').title='Includes authored features, engravings and block modifiers.';
  for(const kind of ['cavity','port','drilling','mounting']){
    const group=element('div',null,'tree-group'),list=draft.features.filter(f=>f.kind===kind);
    group.append(element('div',`${{cavity:'Cavities',port:'External Ports',drilling:'Manual Drillings',mounting:'Mounting Holes'}[kind]} · ${list.length}`,'tree-heading'));
    for(const f of list){
      const btn=element('button',null,'tree-feature');btn.dataset.feature=f.id;
      const interfaceNets=f.interface_nets||{},netId=f.kind==='cavity'?Object.values(interfaceNets)[0]:f.circuit,net=draft.nets.find(n=>n.id===netId);
      const dot=element('span',null,'swatch');dot.style.background=net?.color||colors[netId]||'#b4c7da';
      btn.append(dot,element('span',featureLabel(f,draft)),element('small',f.suppressed?'SUPPRESSED':f.kind==='cavity'?Object.values(interfaceNets).map(id=>displayNetName(draft,id)).join(' / '):f.face));
      btn.classList.toggle('active',selection===f.id);
      btn.onpointerenter=()=>viewer?.hover(f.id);btn.onpointerleave=()=>viewer?.hover(null);
      btn.onclick=()=>select(f.id);group.append(btn);
    }
    tree.append(group);
  }
  const displayed=currentDisplayedDesign();
  const generated=displayed?.features.filter(f=>f.route_net&&!draft.features.some(x=>x.id===f.id))||[];
  if(generated.length){
    const group=element('div',null,'tree-group generated-group');
    group.append(element('div',`Generated Routes · ${generated.length} · ${displayedSource==='retained'?'Retained last usable view':'Current proposal'}`,'tree-heading'));
    for(const f of generated){
      const btn=element('button',null,'tree-feature'),dot=element('span',null,'swatch'),net=displayed.nets.find(n=>n.id===f.route_net);
      dot.style.background=net?.color||colors[f.route_net]||'#b4c7da';
      btn.dataset.feature=f.id;btn.classList.toggle('active',selection===f.id);
      btn.onpointerenter=()=>viewer?.hover(f.id);btn.onpointerleave=()=>viewer?.hover(null);
      btn.append(dot,element('span',featureLabel(f,displayed)),element('small',displayNetName(displayed,f.route_net)));
      btn.onclick=()=>select(f.id);group.append(btn);
    }
    tree.append(group);
  }
  $('circuits').replaceChildren();
  for(const n of draft.nets){
    const btn=element('button',n.label||n.id,'circuit-toggle');
    btn.style.borderColor=n.color||colors[n.id]||'#b08bea';
    btn.classList.toggle('off',viewer?!viewer.circuitVisible(n.id):false);
    btn.setAttribute('aria-pressed',String(!btn.classList.contains('off')));
    btn.onclick=()=>{
      btn.classList.toggle('off');
      btn.setAttribute('aria-pressed',String(!btn.classList.contains('off')));
      viewer?.circuit(n.id,!btn.classList.contains('off'));
    };
    $('circuits').append(btn);
  }
}
let inspectorKind='block';
const inspectorGroups={
  block:{'Project name':'Block dimensions','Length X / mm':'Block dimensions','Width Y / mm':'Block dimensions','Height Z / mm':'Block dimensions',
    'Material / legacy custom text':'Material & stock','Engineering material':'Material & stock','Standard stock cross-section':'Material & stock',
    'Allowable material stress / MPa':'Engineering rules','Pressure safety factor':'Engineering rules','Preferred extra wall margin / mm':'Engineering rules','Minimum wall / mm':'Engineering rules','Design priority':'Engineering rules','Envelope limit X,Y,Z / mm':'Engineering rules','Engineering notes':'Machining & notes'},
  cavity:{'Face':'Position','Replace from Engineering Library':'Definition & cartridge','View Definition':'Definition & cartridge','Duplicate as Custom':'Definition & cartridge','Assign compatible cartridge':'Definition & cartridge'},
  port:{'Face':'Position','Hydraulic net':'Hydraulic & machining','Port specification':'Hydraulic & machining','Diameter / mm':'Hydraulic & machining','Cylinder depth / mm':'Hydraulic & machining','Entry closure':'Hydraulic & machining','Plug engagement / mm':'Hydraulic & machining'},
  drilling:{'Face':'Position','Hydraulic net':'Hydraulic & machining','Diameter / mm':'Hydraulic & machining','Cylinder depth / mm':'Hydraulic & machining','Drill direction X,Y,Z (blank = face normal)':'Hydraulic & machining','Drill point angle / degrees':'Hydraulic & machining'},
  mounting:{'Face':'Position','Diameter / mm':'Mounting specification','Cylinder depth / mm':'Mounting specification','Thread depth / mm':'Mounting specification','Through hole':'Mounting specification'},
};
function inspectorGroupFor(label){
  if(label.includes('→ Net'))return 'Hydraulic interfaces';
  return inspectorGroups[inspectorKind]?.[label]||null;
}
function field(parent,label,value,onChange,options=null,numeric=false){const wrap=element('label',label,'field'),input=document.createElement(options?'select':'input');if(parent===$('inspector'))wrap.dataset.inspectorGroup=inspectorGroupFor(label)||'';input.setAttribute('aria-label',label);if(options)for(const [key,text]of Object.entries(options)){const o=element('option',text);o.value=key;input.append(o);}else{input.type=numeric?'number':'text';if(numeric)input.step='.1';}input.value=value??'';input.onchange=()=>{if(numeric==='optional'&&input.value.trim()===''){onChange(null);return;}const v=numeric?input.valueAsNumber:input.value;if(numeric&&!Number.isFinite(v)){input.reportValidity();return;}onChange(v);};wrap.append(input);parent.append(wrap);return input;}
const prop=(p,l,v,fn,o=null,n=false)=>field(p,l,v,x=>change(()=>fn(x)),o,n);
function action(parent,label,fn){const b=element('button',label);b.type='button';b.onclick=fn;if(parent===$('inspector'))b.dataset.inspectorGroup=inspectorGroupFor(label)||'';parent.append(b);return b;}
function blockMachiningSummary(form){
  const engravings=draft.engravings||[],modifiers=draft.block_modifiers||[];
  if(!engravings.length&&!modifiers.length)return;
  const details=element('details');details.open=true;details.append(element('summary',`Authored block machining · ${engravings.length+modifiers.length}`));form.append(details);
  for(const row of engravings){const item=element('div',null,'port-row');item.append(element('p',`${row.id} · ENGRAVE “${row.text}” · ${row.face} · ${row.text_height} mm high × ${row.depth} mm deep`));action(item,'Remove',()=>change(()=>draft.engravings=draft.engravings.filter(value=>value.id!==row.id)));details.append(item);}
  for(const row of modifiers){const item=element('div',null,'port-row'),spec=row.kind==='chamfer'?`${row.size} mm face-edge chamfer`:`${row.width} × ${row.height} × ${row.depth} mm rectangular cutout`;item.append(element('p',`${row.id} · ${row.face} · ${spec}`));action(item,'Remove',()=>change(()=>draft.block_modifiers=draft.block_modifiers.filter(value=>value.id!==row.id)));details.append(item);}
}
function featureModifierEditor(form,f){
  f.machining_modifiers??=[];if(!modifierCatalog.length&&!f.machining_modifiers.length)return;
  const details=element('details');details.append(element('summary',`Source-backed machining modifiers · ${f.machining_modifiers.length}`));form.append(details);
  for(const placement of f.machining_modifiers){const definition=modifierCatalog.find(row=>row.id===placement.modifier_id),row=element('div',null,'port-row');row.append(element('p',`${definition?.display_name||placement.modifier_id} · starts ${placement.start} mm from entry`));prop(row,'Axial start / mm',placement.start,value=>placement.start=value,null,true);action(row,'Remove',()=>change(()=>f.machining_modifiers=f.machining_modifiers.filter(value=>value!==placement)));details.append(row);}
  const usable=modifierCatalog.filter(row=>!f.machining_modifiers.some(value=>value.modifier_id===row.id)).sort((a,b)=>(a.unit_system===draft.project_context?-1:1)-(b.unit_system===draft.project_context?-1:1)||a.display_name.localeCompare(b.display_name));if(usable.length){let selected=usable[0].id;field(details,'Add modifier',selected,value=>selected=value,Object.fromEntries(usable.map(row=>[row.id,`${row.display_name} · ${row.kind} · ${row.unit_system} native`])));action(details,'Add source-backed modifier',()=>change(()=>f.machining_modifiers.push({modifier_id:selected,start:0})));}
}
function newId(prefix){let i=1;while(draft.features.some(f=>f.id===prefix+i))i++;return prefix+i;}
function replaceCavity(f,id){
  const def=draft.library.find(d=>d.id===id);if(!def||!isCavity(def)){notice('Replacement must be a cavity.',true);return;}const existing=f.interface_nets||{},mapping=Object.fromEntries(def.zones.map(z=>[z.id,existing[z.id]||'']));
  const apply=()=>change(()=>{if(Object.values(mapping).some(n=>!n))throw Error('Choose a net for every new interface');f.cavity_id=id;f.interface_nets={...mapping};f.cartridge_id=null;[f.u,f.v]=clamp(f,draft,f.u,f.v);const valid=new Set(def.zones.map(z=>`${f.id}:${z.id}`));for(const bore of draft.features)bore.connects_to=bore.connects_to.filter(t=>!t.startsWith(f.id+':')||valid.has(t));});
  if(def.zones.length===Object.keys(existing).length&&Object.values(mapping).every(Boolean)){apply();return;}
  $('workflow-title').textContent='Replace cavity · confirm interface mapping';const box=$('workflow-content');box.replaceChildren(element('p','The new cavity has different hydraulic windows. Assign every new window explicitly. Removed windows will lose their physical contact declarations; schematic mapping must be reviewed.'));
  for(const z of def.zones)field(box,`New interface ${z.id}`,mapping[z.id],v=>mapping[z.id]=v,{'':'Select hydraulic net',...Object.fromEntries(draft.nets.map(n=>[n.id,n.label||n.id]))});
  action(box,'Apply replacement',()=>{if(Object.values(mapping).some(n=>!n)){$('workflow-error').textContent='Choose a net for every interface';return;}apply();$('workflow-dialog').close();});$('workflow-error').textContent='';$('workflow-dialog').showModal();select(f.id);
}
async function assignCartridge(f){
  $('workflow-title').textContent='Cartridge assignment · '+f.id;const box=$('workflow-content');box.replaceChildren(element('p','Only cartridges with an explicit database compatibility relationship are available. Leaving this empty is valid.'));$('workflow-error').textContent='';$('workflow-dialog').showModal();
  action(box,'No cartridge',()=>{change(()=>f.cartridge_id=null);$('workflow-dialog').close();select(f.id);});
  try{const result=await api('/api/cavities/'+encodeURIComponent(f.cavity_id)+'/cartridges');for(const row of result.items){const card=element('section',null,'library-card');card.append(element('h3',row.model),element('p',`${row.manufacturer||'Manufacturer unspecified'} · ${row.function||'Function unspecified'}\n${row.id}`));action(card,'Assign cartridge',()=>{change(()=>f.cartridge_id=row.id);$('workflow-dialog').close();select(f.id);});box.append(card);}if(!result.items.length)box.append(element('p','No compatible cartridges are present in the engineering database. The cavity remains valid without one.'));}catch(e){$('workflow-error').textContent=e.message;}
}
function remove(id){change(()=>{const ids=new Set([id]);let n;do{n=ids.size;for(const f of draft.features)if(ids.has(f.parent_id))ids.add(f.id);}while(ids.size!==n);draft.features=draft.features.filter(f=>!ids.has(f.id));for(const f of draft.features)f.connects_to=f.connects_to.filter(t=>!ids.has(t.split(':')[0]));for(const c of draft.schematic_intent?.components||[])if(ids.has(c.placement_id)){c.placement_id=null;c.cavity_id=null;}selection='block';});}
function rerouteNet(netId){change(()=>{returnNetToAutomatic(draft,netId);selection='block';});notice(`Net ${netId} returned to automatic routing. A fresh route will be generated by the current preview.`);}

const inspectorOpenByKind=new Map();
function organizeInspector(kind){
  const form=$('inspector'),nodes=[...form.children];
  const headers=nodes.filter(node=>node.classList?.contains('inspector-title')||kind==='generated'&&['H3','BUTTON'].includes(node.tagName)||kind!=='block'&&node.classList?.contains('action-row')&&node===nodes.find(item=>item.classList?.contains('action-row')));
  form.replaceChildren(...headers);
  const defaultGroup=kind==='block'?'Block dimensions':kind==='generated'?'Route details':'Position';
  let current='',section=null,body=null,positionComplete=false;
  const opening=(name)=>{
    if(current===name)return;
    current=name;
    section=element('details',null,'inspector-section');
    section.dataset.section=name;
    const key=kind+':'+name;
    section.open=inspectorOpenByKind.has(key)?inspectorOpenByKind.get(key):name!=='Advanced / Developer information';
    const summary=element('summary',name);
    const ownSection=section;
    ownSection.addEventListener('toggle',()=>inspectorOpenByKind.set(key,ownSection.open));
    section.append(summary);
    body=element('div',null,'section-body');section.append(body);form.append(section);
  };
  for(const node of nodes){
    if(headers.includes(node))continue;
    if(node.tagName==='DETAILS'&&node.querySelector('summary')?.textContent==='Advanced / Developer information'){
      node.classList.add('inspector-section');
      const key=kind+':advanced';
      node.open=inspectorOpenByKind.get(key)||false;
      node.addEventListener('toggle',()=>inspectorOpenByKind.set(key,node.open));
      form.append(node);continue;
    }
    let name=node.dataset.inspectorGroup||current||defaultGroup;
    if(!node.dataset.inspectorGroup&&node.classList?.contains('property-note')){
      if(positionComplete&&current==='Position'&&kind==='mounting')name='Mounting specification';
      else if(positionComplete&&current==='Position'&&['port','drilling'].includes(kind))name='Hydraulic & machining';
      else if(kind==='cavity'&&current==='Hydraulic interfaces')name='Source machining info';
    }
    opening(name);
    body.append(node);
    if(node.classList?.contains('field-row'))positionComplete=true;
  }
}
function finishSelection(kind,previous){
  for(const button of document.querySelectorAll('[data-feature]'))button.classList.toggle('active',button.dataset.feature===selection);
  $('select-block').classList.toggle('active',selection==='block');
  const summary=$('feature-results');
  summary.replaceChildren();
  if(report){
    const heading=reportSource({report,build:state?.build,dirty,stale:state?.stale,externalChange,draftCheckedSignature,draftSignature:JSON.stringify(draft),displayedDraftSignature,displayedSource,reportWasDraft}).label;
    const checks=report.checks.filter(c=>c.status!=='PASS'&&c.items.some(item=>item.split(':')[0]===selection));
    if(checks.length)summary.append(element('div',heading,'issue-source'));
    for(const check of checks){
      const issue=element('div',null,'feature-check');
      issue.append(element('strong',check.status+' · '+displayRuleName(check.rule)),
        element('span','Actual: '+check.actual+' '+(check.unit||'')),
        element('span','Required: '+check.required+' '+(check.unit||'')));
      summary.append(issue);
    }
  }
  organizeInspector(kind);
  if($('report-filter').value==='selected'){renderReport();renderHeader();}
  if(previous!==selection){
    const target=[...document.querySelectorAll('#feature-tree [data-feature]')].find(node=>node.dataset.feature===selection);
    if(target){const list=document.querySelector('.tree-scroll'),item=target.getBoundingClientRect(),area=list.getBoundingClientRect();
      if(item.top<area.top||item.bottom>area.bottom)target.scrollIntoView({block:'nearest'});
    }
  }
}
function select(id){if(!draft)return;inspectorKind=id==='block'?'block':draft.features.find(item=>item.id===id)?.kind||'generated';const previous=selection;if(id!==previous)viewer?.setSecondary([]);const displayed=currentDisplayedDesign(),generated=displayed?.features.find(f=>f.id===id&&f.route_net&&!draft.features.some(x=>x.id===id));if(generated){const label=featureLabel(generated,displayed),netLabel=displayNetName(displayed,generated.route_net);selection=id;viewer?.select(id);$('selection-label').textContent=label;$('selection-kind').textContent='GENERATED ROUTE';const form=$('inspector');form.replaceChildren(element('h3',label),element('p',`${netLabel} hydraulic route · ${generated.face} · Ø${generated.diameter} × ${generated.depth.toFixed(2)} mm`),element('p','Refine this route to keep its current segments and drag drilling handles. Connected branches are extended where possible; exact checks decide whether the edited route still works.'));action(form,'Refine in 3D',()=>adoptRoute(generated.route_net,id));finishSelection('generated',previous);return;}selection=draft.features.some(f=>f.id===id)?id:'block';viewer?.select(selection);$('selection-label').textContent=selection==='block'?'':featureLabel(draft.features.find(f=>f.id===selection),draft);for(const b of document.querySelectorAll('[data-feature]'))b.classList.toggle('active',b.dataset.feature===selection);$('select-block').classList.toggle('active',selection==='block');const form=$('inspector');form.replaceChildren();form.onsubmit=e=>e.preventDefault();
if(selection==='block'){$('selection-kind').textContent='STOCK';form.append(element('div','MANIFOLD','inspector-title'));prop(form,'Project name',draft.name,v=>draft.name=v);for(const [key,label]of [['length','Length X / mm'],['width','Width Y / mm'],['height','Height Z / mm']])prop(form,label,draft.block[key],v=>draft.block[key]=v,null,true);prop(form,'Material / legacy custom text',draft.block.material,v=>draft.block.material=v);if(materialCatalog.length){prop(form,'Engineering material',draft.block.material_id||'',v=>{draft.block.material_id=v||null;draft.block.stock_id=null;draft.block.stock_dimensions=null;draft.block.machining_allowance=null;draft.block.stock_excess=null;const m=materialCatalog.find(row=>row.id===v);if(m)draft.block.material=m.display_name;},{'':'Legacy/custom material',...Object.fromEntries(materialCatalog.map(row=>[row.id,row.display_name]))});const material=materialCatalog.find(row=>row.id===draft.block.material_id),stock=(material?.stock||[]).filter(row=>(row.size_1_mm>=draft.block.width+2*row.allowance_1_mm&&row.size_2_mm>=draft.block.height+2*row.allowance_2_mm)||(row.size_2_mm>=draft.block.width+2*row.allowance_2_mm&&row.size_1_mm>=draft.block.height+2*row.allowance_1_mm)).sort((a,b)=>(a.unit_system===draft.project_context?-1:1)-(b.unit_system===draft.project_context?-1:1)||a.size_1_mm-b.size_1_mm||a.size_2_mm-b.size_2_mm);if(material)prop(form,'Standard stock cross-section',draft.block.stock_id||'',v=>{draft.block.stock_id=v||null;const row=stock.find(item=>item.id===v);if(row){const direct=row.size_1_mm>=draft.block.width+2*row.allowance_1_mm&&row.size_2_mm>=draft.block.height+2*row.allowance_2_mm,y=direct?row.size_1_mm:row.size_2_mm,z=direct?row.size_2_mm:row.size_1_mm,ay=direct?row.allowance_1_mm:row.allowance_2_mm,az=direct?row.allowance_2_mm:row.allowance_1_mm;draft.block.stock_dimensions=[draft.block.length,y,z];draft.block.machining_allowance=[0,ay,az];draft.block.stock_excess=[0,(y-draft.block.width)/2,(z-draft.block.height)/2];}else{draft.block.stock_dimensions=null;draft.block.machining_allowance=null;draft.block.stock_excess=null;}},{'':'No standard blank selected',...Object.fromEntries(stock.map(row=>[row.id,`${row.size_1_mm.toFixed(2)} × ${row.size_2_mm.toFixed(2)} mm · ${row.unit_system} native`]))});if(draft.block.stock_id)form.append(element('p',`Required machining allowance: ${draft.block.machining_allowance.map(v=>v.toFixed(2)).join(' / ')} mm\nActual stock excess: ${draft.block.stock_excess.map(v=>v.toFixed(2)).join(' / ')} mm`,'property-note'));}prop(form,'Allowable material stress / MPa',(draft.rules.allowable_stress_mpa??''),v=>draft.rules.allowable_stress_mpa=v==null?null:v,null,'optional');prop(form,'Pressure safety factor',draft.rules.pressure_safety_factor??2,v=>draft.rules.pressure_safety_factor=v,null,true);prop(form,'Preferred extra wall margin / mm',draft.constraints.preferred_wall_margin,v=>draft.constraints.preferred_wall_margin=v,null,true);prop(form,'Minimum wall / mm',draft.rules.minimum_wall,v=>draft.rules.minimum_wall=v,null,true);prop(form,'Design priority',draft.constraints.priority,v=>draft.constraints.priority=v,{compact:'Compact envelope',fewer_plugs:'Fewer plugs',simple_machining:'Simpler machining',short_drills:'Shorter drillings'});prop(form,'Envelope limit X,Y,Z / mm',(draft.constraints.envelope_max||[]).join(', '),v=>draft.constraints.envelope_max=v.trim()?v.split(',').map(Number):null);prop(form,'Engineering notes',draft.constraints.notes,v=>draft.constraints.notes=v);form.append(element('p','Finished CAD dimensions stay independent from selected source-backed stock. MDTools material rows do not supply allowable stress, fatigue, corrosion or pressure ratings.','inspector-note'));blockMachiningSummary(form);}
else{const f=draft.features.find(f=>f.id===selection);const p=pose(f,draft.block),uv=axes[f.face];form.append(element('p',`Origin XYZ: ${p.origin.map(x=>x.toFixed(3)).join(', ')} mm · U=+${'XYZ'[uv[0]]}, V=+${'XYZ'[uv[1]]} · inward ${p.direction.join(', ')}`,'property-note'));$('selection-kind').textContent=f.kind.toUpperCase();form.append(element('div',featureLabel(f,draft),'inspector-title'));if(f.frozen_net)form.append(element('p',`Refined ${displayNetName(draft,f.frozen_net)} route. Drag anywhere along the drilling to check changes.${!f.plugged?' This entry uses a fixed external port; lateral moves may invalidate its closure.':''}`,'property-note'));const bar=element('div',null,'action-row');form.append(bar);action(bar,'Duplicate',()=>change(()=>{const copy=structuredClone(f);copy.id=newId(f.kind==='cavity'?'CV':f.kind==='port'?f.circuit.slice(0,36):f.kind==='mounting'?'MNT':'DRILL');copy.parent_id=null;copy.schematic_id='';copy.connects_to=[];[copy.u,copy.v]=clamp(copy,draft,copy.u+25,copy.v+20);draft.features.push(copy);selection=copy.id;}));action(bar,f.suppressed?'Restore':'Suppress',()=>change(()=>f.suppressed=!f.suppressed));action(bar,f.frozen_net?'Delete & Return to Automatic Routing':'Delete',()=>f.frozen_net?rerouteNet(f.frozen_net):remove(f.id));prop(form,'Face',f.face,v=>{f.face=v;if(f.kind==='mounting'&&f.through)f.depth=[draft.block.length,draft.block.width,draft.block.height][axes[f.face][2]];[f.u,f.v]=clamp(f,draft,f.u,f.v);},faces);const row=element('div',null,'field-row');form.append(row);prop(row,'Position U / mm',f.u,v=>{[f.u,f.v]=clamp(f,draft,v,f.v);},null,true);prop(row,'Position V / mm',f.v,v=>{[f.u,f.v]=clamp(f,draft,f.u,v);},null,true);
if(f.kind==='cavity'){action(form,'Replace from Engineering Library',()=>workflowHandlers.replaceFromLibrary(f));action(form,'View Definition',()=>workflowHandlers.viewDefinition(f));action(form,'Duplicate as Custom',()=>workflowHandlers.duplicateDefinition(f));form.append(element('p','Cartridge: '+(f.cartridge_id||'None'),'property-note'));action(form,'Assign compatible cartridge',()=>assignCartridge(f));for(const [index,key] of Object.keys(f.interface_nets||{}).entries())prop(form,`${displayInterfaceName(draft,f.id,key,{index})} → Net`,f.interface_nets[key],v=>f.interface_nets[key]=v,Object.fromEntries(draft.nets.map(n=>[n.id,n.label||n.id])));const def=draft.library.find(d=>d.id===f.cavity_id);form.append(element('p',`${def.manufacturer||'Manufacturer unspecified'} · ${def.family||'Family unspecified'}\n${def.label}\n${def.stages.map(s=>`Ø${s.diameter.toFixed(4)} / ${s.start.toFixed(4)}–${s.end.toFixed(4)} mm`).join('\n')}`,'property-note'));}
else if(f.kind==='mounting'){if((f.mounting_mode||'plain')==='threaded'){const thread=draft.threads?.find(row=>row.id===f.thread_definition_id);form.append(element('p',`${thread?.display_name||f.thread_definition_id} THD · thread depth ${f.thread_depth} mm${thread?.tap_diameter_mm?` · tap Ø${Number(thread.tap_diameter_mm).toFixed(3)} mm`:''}`,'property-note'));prop(form,'Thread depth / mm',f.thread_depth,v=>f.thread_depth=v,null,true);}else prop(form,'Diameter / mm',f.diameter,v=>f.diameter=v,null,true);prop(form,'Through hole',String(f.through),v=>{f.through=v==='true';if(f.through){f.tip_angle=180;f.depth=[draft.block.length,draft.block.width,draft.block.height][axes[f.face][2]];if(f.mounting_mode==='threaded')f.thread_depth=f.depth;}},{true:'Through',false:'Blind'});if(!f.through){prop(form,'Cylinder depth / mm',f.depth,v=>f.depth=v,null,true);prop(form,'Drill point angle / degrees',f.tip_angle,v=>f.tip_angle=v,null,true);}form.append(element('p',(f.mounting_mode==='threaded'?'SQLite thread identity; exact BRep uses the source tap/minor bore without helical faces.':'Plain non-hydraulic mounting cut. No thread or fastener compatibility is inferred.')+' Exact wall and interference checks apply.','property-note'));}
else{if(f.frozen_net)form.append(element('p',`Hydraulic owner: ${displayNetName(draft,f.frozen_net)}. Return this net to automatic routing before changing route intent.`,'property-note'));else prop(form,'Hydraulic net',f.circuit,v=>f.circuit=v,Object.fromEntries(draft.nets.map(n=>[n.id,n.label||n.id])));if(f.port_definition_id){const d=draft.library.find(d=>d.id===f.port_definition_id);form.append(element('p',d.label+' · SQLite machining definition','property-note'));const cuts=d.cutting_primitives?.length?d.cutting_primitives:d.stages;form.append(element('p',`Machining: ${cuts.length} mapped cuts · axial span ${Math.min(...cuts.map(s=>s.start)).toFixed(2)}–${Math.max(...cuts.map(s=>s.end)).toFixed(2)} mm.\nHydraulic window: ${d.zones.map(z=>`Ø${z.diameter.toFixed(2)} envelope at ${z.start.toFixed(2)}–${z.end.toFixed(2)} mm${z.clip_to_cut?' (clipped to machining)':''}`).join(', ')}.`,'property-note'));}else for(const key of ['diameter','depth'])prop(form,key==='diameter'?'Diameter / mm':'Cylinder depth / mm',f[key],v=>f[key]=v,null,true);if(f.kind==='port')prop(form,'Port specification',f.size,v=>f.size=v);else{prop(form,'Drill direction X,Y,Z (blank = face normal)',(f.direction||[]).join(', '),v=>f.direction=v.trim()?v.split(',').map(Number):null);prop(form,'Entry closure',String(f.plugged),v=>f.plugged=v==='true',{'true':'Plug','false':'Coaxial external port'});prop(form,'Drill point angle / degrees',f.tip_angle,v=>f.tip_angle=v,null,true);prop(form,'Plug engagement / mm',f.plug_length,v=>f.plug_length=v,null,true);if(f.plugged)form.append(element('p','Plug engagement is a declared closure volume. No source entry profile is bound; machining details remain unresolved.','property-note'));}}
featureModifierEditor(form,f);const advanced=element('details');advanced.append(element('summary','Advanced / Developer information'));form.append(advanced);advanced.append(element('p','Internal reference: '+f.id,'property-note'));prop(advanced,'Rotation / degrees',f.rotation,v=>f.rotation=v,null,true);prop(advanced,'Parent feature',f.parent_id||'',v=>{f.parent_id=v||null;const p=draft.features.find(x=>x.id===v);if(p)f.local_offset=[f.u-p.u,f.v-p.v];},{'':'Independent',...Object.fromEntries(draft.features.filter(x=>x.id!==f.id).map(x=>[x.id,featureLabel(x,draft)]))});prop(advanced,'Machining ID',f.machining_id,v=>f.machining_id=v);if(f.kind==='drilling')prop(advanced,'Expected contacts',f.connects_to.join(', '),v=>f.connects_to=v.split(',').map(s=>s.trim()).filter(Boolean));advanced.append(element('p','Rotation moves attached offsets and native footprint cuts.','inspector-note'));for(const [n,t]of Object.entries(report?.graph||{}).filter(([n])=>n===f.id||n.startsWith(f.id+':')))advanced.append(element('div',`${displayIdentity(reportDesign||currentDisplayedDesign()||draft,n)} → ${t.map(value=>displayIdentity(reportDesign||currentDisplayedDesign()||draft,value)).join(', ')||'Disconnected'} (last build)`,'property-note'));}
finishSelection(selection==='block'?'block':draft.features.find(f=>f.id===selection).kind,previous);}
function renderReport(){
  if(!report){
    $('check-counts').textContent='Not validated';
    $('validation-results').replaceChildren(element('p','Validate to check this project.'));
    $('limitations').replaceChildren();
    $('build-time').textContent='';
    viewer?.setIssueMarkers([]);
    return;
  }
  const draftSignature=JSON.stringify(draft),displayed=currentDisplayedDesign();
  const source=reportSource({report,build:state?.build,dirty,stale:state?.stale,externalChange,draftCheckedSignature,draftSignature,displayedDraftSignature,displayedSource,reportWasDraft});
  $('check-counts').textContent=`${source.label} · ${report.counts.PASS} PASS / ${report.counts.WARNING} WARNING / ${report.counts.FAIL} FAIL`;
  $('build-time').textContent=new Date(report.generated_at).toLocaleString();
  $('limitations').replaceChildren(...report.limitations.map(s=>element('li',s)));
  viewer?.setIssueMarkers(source.spatial?issueReferences(report,{displayed,draft}):[]);
  const filter=$('report-filter').value;
  const checks=report.checks.filter(c=>filter==='all'||(filter==='issues'?c.status!=='PASS':c.items.some(i=>i.split(':')[0]===selection)));
  const container=$('validation-results');
  container.replaceChildren();
  if(!checks.length){
    container.append(element('div','No issues in this build’s selected checks. Geometry results are not a pressure or manufacturing certification.','pass-message'));
    return;
  }
  const table=element('table',null,'check-table'),head=element('tr');
  for(const t of ['Status','Rule','Items','Actual','Required','Source / Locate'])head.append(element('th',t));
  table.append(head);
  for(const c of checks){
    const row=element('tr');
    row.title=c.message;
    const targets=resolveCheckTargets(c,{displayed,draft});
    row.append(
      element('td',c.status,c.status),
      element('td',displayRuleName(c.rule)),
      element('td',c.items.map(item=>displayIdentity(source.kind==='draft'?displayed:reportDesign||displayed||draft,item)).join(' ↔ ')),
      element('td',`${c.actual} ${c.unit}`),
      element('td',`${c.required} ${c.unit||''}`)
    );
    const sourceCell=element('td');
    if(targets.ids.length){
      const locate=action(sourceCell,source.spatial?'Locate affected objects':displayedSource==='retained'?'View retained model reference':'View current object reference',()=>{
        if(targets.primary)select(targets.primary);
        viewer?.setSecondary(targets.secondary);
        const result=viewer?.frame(targets.ids);
        if(!result?.ok)notice(result?.reason||'The displayed objects cannot be framed.',true);
        else if(!source.spatial)notice(displayedSource==='retained'?'Showing references in the retained last usable model. These results are not current spatial evidence.':'Showing current object references. These results belong to a previous build.');
      });
      locate.className='locate-check';locate.title=source.label;
    }else sourceCell.textContent='No spatial reference';
    row.append(sourceCell);
    table.append(row);
  }
  container.append(table);
}
async function load(key=state?.project_id){if(!key)return;const preserveView=key===state?.project_id&&!document.body.classList.contains('home');const epoch=++projectEpoch;previews.cancel();const next=await api('/api/projects/'+key);let nr,nm,nd,reviewError;if(next.build)[nr,nm,nd]=await Promise.all(['validation.json','review.json','resolved_design.json'].map(n=>api(`/api/artifacts/${next.build.build_id}/${n}`).catch(()=>null)));if(epoch!==projectEpoch)return;lastUsablePreview=null;exactPreview=null;draftCheckedSignature=null;displayedDraftSignature=null;displayedSource='none';if(nm?.geometry_kind==='unavailable'){reviewError=nm.review_error;nm=null;}if(!preserveView){viewer?.resetTransient();isolateButton.textContent='Isolate';clipEnable.checked=false;clipNotice.hidden=true;selection='block';}state=next;const networkLabel=document.querySelector('.local-dot');networkLabel.textContent=next.network?.mode==='lan'?'LAN workspace':'Local workspace';networkLabel.title=(next.network?.urls||[]).join('\n');draft=hydrateDesign(structuredClone(next.design),next.engineering?.definitions,next.engineering?.threads);report=nr;reportWasDraft=false;reportDesign=nd?hydrateDesign(nd,next.engineering?.definitions,next.engineering?.threads):null;model=next.stale?null:nm;resolved=next.stale?draft:hydrateDesign(nd||draft,next.engineering?.definitions,next.engineering?.threads);viewer?.setReferences(resolved.features);dirty=false;externalChange=false;previews.cancel();if(!model){viewer?.preview(draft);markDisplayed(draft,'draft');lastUsablePreview={design:cloneDesign(draft),draftSignature:displayedDraftSignature};}if(model){viewer?.load(model,resolved);markDisplayed(draft,'authoritative');lastUsablePreview={model,design:resolved,draftSignature:displayedDraftSignature};previewState('authoritative',`AUTHORITATIVE VALIDATION · ${next.build.status} · EXACT OCCT BREP · ${(model.volume_mm3/1000).toFixed(1)} cm³`);}viewer?.setDesign(draft);document.body.classList.remove('home');if(!preserveView)viewer?.fit($('face-view').value);if(!model)refreshPreview();if(!dragStart)requestSolid();renderTree();select(selection);renderReport();renderHeader();notice(reviewError&&!state.stale?reviewError+' Authoritative Validate: '+state.build.status:state.stale?'Project is newer than this build. Validate to update.':'Select a cavity, external port, or hydraulic route.');}
async function build(){
  if(busy||!state)return;
  if(!state.project_id){try{await saveProject();}catch(error){notice(error.message,true);return;}}
  if(busy)return;
  busy=true;previews.cancel();document.body.classList.add('busy');
  shell.setBusy(true);viewer?.editing(false);
  const disabledBefore=new Map();
  const lockControl=control=>{if(disabledBefore.has(control))return;disabledBefore.set(control,control.disabled);control.disabled=true;};
  document.querySelectorAll('button,input,select,textarea').forEach(lockControl);
  const busyObserver=new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes){if(node.nodeType!==1)continue;if(node.matches?.('button,input,select,textarea'))lockControl(node);node.querySelectorAll?.('button,input,select,textarea').forEach(lockControl);}});
  busyObserver.observe(document.body,{childList:true,subtree:true});
  renderHeader();notice('Running exact cuts, connectivity, wall checks and STEP round trip…');
  try{
    await post('/api/build',{expected_revision:state.revision,design:dirty?draft:null,project_id:state.project_id});
    await load();history=[];future=[];
    shell.validationCompleted(report);
  }catch(error){notice(error.message,true);}
  finally{
    busy=false;viewer?.editing(true);document.body.classList.remove('busy');
    busyObserver.disconnect();
    for(const [control,wasDisabled] of disabledBefore)if(control.isConnected)control.disabled=wasDisabled;
    shell.setBusy(false);renderHeader();if(draft){renderReport();select(selection);}
  }
}
$('build').onclick=build;$('select-block').onclick=()=>select('block');$('reload').onclick=async()=>{if(dirty&&!confirm('Discard unsaved draft and reload?'))return;try{await load();history=[];future=[];renderHeader();}catch(e){notice(e.message,true);}};$('undo').onclick=()=>{if(history.length){future.push(cloneDesign(draft));draft=history.pop();markDirty();renderTree();select(selection);}};$('redo').onclick=()=>{if(future.length){history.push(cloneDesign(draft));draft=future.pop();markDirty();renderTree();select(selection);}};
$('fit').onclick=()=>viewer?.fit();$('face-view').onchange=e=>viewer?.setView(e.target.value);for(const mode of ['review','solid','void','features'])$(mode+'-mode').onclick=()=>{viewMode=mode;viewer?.mode(mode);isolateButton.textContent='Isolate';requestLayer(mode);for(const key of ['review','solid','void','features'])$(key+'-mode').classList.toggle('active',mode===key);shell.syncMode(mode);};$('opacity').oninput=e=>{viewer?.opacity(Number(e.target.value)/100);$('opacity-value').textContent=e.target.value+'%';};for(const key of ['cavities','ports','closures','zones','drillings','labels'])$('show-'+key).onchange=e=>viewer?.toggle(key,e.target.checked);$('show-xray').onchange=e=>viewer?.xray(e.target.checked);$('report-filter').onchange=()=>{renderReport();renderHeader();};$('json-open').onclick=()=>{$('json-editor').value=JSON.stringify(draft,null,2);$('json-error').textContent='';$('json-dialog').showModal();};$('json-close').onclick=()=>$('json-dialog').close();$('json-apply').onclick=async()=>{try{const value=await post('/api/check-design',JSON.parse($('json-editor').value));change(()=>draft=hydrateDesign(value,draft.library,draft.threads));$('json-dialog').close();}catch(e){$('json-error').textContent=e.message;}};
document.addEventListener('keydown',event=>{
  if(event.defaultPrevented||event.isComposing||document.querySelector('dialog[open]'))return;
  const target=event.target;
  if(target?.closest?.('input,textarea,select,[contenteditable="true"]')||document.body.classList.contains('home'))return;
  if(event.key==='f'&&!event.repeat&&!event.ctrlKey&&!event.altKey&&!event.metaKey){event.preventDefault();focusButton.click();return;}
  if(event.key!=='Escape')return;
  if(shell.closeTopLayer()){event.preventDefault();return;}
  if(viewer?.cancelInteraction()){event.preventDefault();return;}
  if(viewer?.clearIsolation()){event.preventDefault();isolateButton.textContent='Isolate';return;}
  if(viewer?.inspection().clipping.enabled){event.preventDefault();clipReset.click();}
});
async function persistProject(){
  const epoch=projectEpoch,signature=JSON.stringify(draft),key=state?.project_id||null,expected=state?.revision;
  const result=await post('/api/projects',{design:draft,project_id:key,expected_revision:key?expected:null});
  if(epoch!==projectEpoch||(state?.project_id||null)!==key)throw Error('Saved the previous project; another project is now open.');
  state=result;dirty=JSON.stringify(draft)!==signature;externalChange=false;
  if(!dirty){history=[];future=[];}renderHeader();notice(dirty?'Saved the submitted version; newer draft edits still need saving.':'Saved to Projects. Geometry validation is independent of saving.');return result;
}
async function saveProject(){if(savePending)return savePending;$('save-project').disabled=true;savePending=persistProject();try{return await savePending;}finally{savePending=null;$('save-project').disabled=busy;}}
$('save-project').onclick=()=>saveProject().catch(e=>notice(e.message,true));
$('drawings-open').onclick=async()=>{try{if(!state?.project_id||dirty)await saveProject();location.href='/drawing.html?project='+state.project_id;}catch(e){notice(e.message,true);}};
function newProject(value,definitions={},threads={}){if(busy)return false;if(dirty&&!confirm('Discard the current unsaved draft and start this project?'))return false;++projectEpoch;viewer?.resetTransient();isolateButton.textContent='Isolate';clipEnable.checked=false;clipNotice.hidden=true;draft=hydrateDesign(structuredClone(value),definitions,threads);state={design:draft,revision:'0'.repeat(64),build:null,stale:true};report=null;reportWasDraft=false;reportDesign=null;model=null;resolved=draft;viewer?.setReferences(draft.features);history=[];future=[];selection='block';previews.cancel();lastUsablePreview=null;exactPreview=null;solidStatus();viewMode='review';viewer?.mode('review');shell.syncMode('review');$('review-mode').classList.add('active');for(const key of ['solid','void','features'])$(key+'-mode').classList.remove('active');document.body.classList.remove('home');renderReport();markDirty();renderTree();select('block');viewer?.fit();return true;}
const workflowHandlers=workflows({newProject,adoptRoute,replaceCavity,$,element,field,action,api,post,get:()=>draft,state:()=>state,change,set:value=>{draft=hydrateDesign(value,draft?.library||[],draft?.threads||[]);},newId,select,notice,resolved:()=>displayedSource==='retained'?null:currentDisplayedDesign()});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});setInterval(async()=>{if(statusPollPending||!state?.project_id||busy||document.body.classList.contains('home')||document.hidden||document.querySelector('dialog[open]'))return;statusPollPending=true;try{const next=await api('/api/projects/'+state.project_id+'/status');if(next.revision!==state.revision||next.build?.build_id!==state.build?.build_id||next.stale!==state.stale){if(!dirty)await load();else{externalChange=true;renderHeader();notice('Project changed on disk. Draft preserved; reload before saving.',true);}}}catch(e){externalChange=true;renderHeader();notice('Local service unavailable: '+e.message,true);}finally{statusPollPending=false;}},5000);const hub=projectLibrary({onDeleted:id=>{if(state?.project_id===id){++projectEpoch;viewer?.resetTransient();previews.cancel();lastUsablePreview=null;draft=null;state=null;dirty=false;}},$,element,action,api,post,openProject:load,isDirty:()=>dirty,hasProject:()=>!!draft});hub.show();

const requestedProject=new URLSearchParams(location.search).get("project");
if(/^[0-9a-f]{32}$/.test(requestedProject||""))load(requestedProject).catch(e=>notice(e.message,true));
