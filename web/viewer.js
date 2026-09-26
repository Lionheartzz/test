import {createReferenceState} from './viewer-references.js';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { axes, pose, clamp, smartAlign, featureLabel } from './kinematics.js';
import { VIEW_DIRECTIONS, CORNER_VIEWS, viewDirection, cameraSpan, resizeCamera, frameCamera } from './viewer-navigation.js';

export function createViewer(container, onSelect, onDrag = ()=>{}, {onHover=()=>{},onViewChange=()=>{},onMarkerSelect=()=>{}} = {}) {
  const scene = new THREE.Scene();
  const perspective = new THREE.PerspectiveCamera(38, 1, .1, 10000);
  const orthographic = new THREE.OrthographicCamera(-100,100,100,-100,.1,10000);
  perspective.up.set(0, 0, 1);orthographic.up.set(0, 0, 1);
  let camera = perspective, orthoSpan = 200;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.localClippingEnabled = true;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0, 0);
  renderer.domElement.setAttribute('aria-label','Interactive manifold model');
  container.append(renderer.domElement);
  const labels = new CSS2DRenderer();
  Object.assign(labels.domElement.style, { position: 'absolute', top: '0', pointerEvents: 'none' });
  container.append(labels.domElement);
  const collisionNotice=document.createElement('div');collisionNotice.className='collision-notice';collisionNotice.hidden=true;
  const collisionText=document.createElement('span'),collisionButton=document.createElement('button');
  collisionButton.type='button';collisionButton.textContent='Isolate exact contact';
  collisionNotice.append(collisionText,collisionButton);container.append(collisionNotice);
  let isolation=null, clipping={enabled:false,axis:'x',position:0,keep:'gte'};
  const clipPlane=new THREE.Plane(new THREE.Vector3(1,0,0),0);
  collisionButton.onclick=()=>{isolation=isolation?.kind==='contact'?null:{kind:'contact',netPair:null};updateVisibility();};
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.addEventListener('change',()=>onViewChange(navigationState()));
  scene.add(new THREE.HemisphereLight(0xe8f4ff, 0x526478, 2.6));
  for (const [position, intensity] of [[[100, -200, 400], 3], [[-200, 200, 180], 1.8]]) {
    const light = new THREE.DirectionalLight(0xffffff, intensity);
    light.position.set(...position); scene.add(light);
  }
  let group = new THREE.Group(), labelGroup = new THREE.Group(), dragGroup=new THREE.Group(), grid;
  scene.add(group, labelGroup,dragGroup);
  const reference=new THREE.Group(),guides=new THREE.Group();scene.add(reference,guides);
  function clipMaterial(material){material.clippingPlanes=clipping.enabled?[clipPlane]:[];return material;}
  function guideLine(a,b,color){const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a),new THREE.Vector3(...b)]),clipMaterial(new THREE.LineBasicMaterial({color,depthTest:false})));line.renderOrder=20;guides.add(line);}

  let block, mode = 'review', opacity = .22, xray = false, selected = 'block', machinedBody=false, pendingFit=null;
  let deferredLayers=new Set(),loadedLayers=new Set(),dragOwners=new Set();const diagnostics=[];
  const references=createReferenceState();
  let renderedFeatures=[], design, displayContext, displayPlacements={}, editing = true, handles = new THREE.Group(); scene.add(handles);
  const frameBoundsCache=new Map();
  const hitAreas = new THREE.Group(); scene.add(hitAreas);
  let hovered = null;const boundaryGroup=new THREE.Group(),markerGroup=new THREE.Group(),localGizmo=new THREE.Group();scene.add(boundaryGroup,markerGroup,localGizmo);
  let secondary=new Set(),issueRows=[];
  const visible = { cavities: true, ports: true, closures: true, zones: true, drillings: true, labels: true, circuits: new Set(['P', 'T', 'A', 'B', 'LS', 'Drain']) };
  function disposeGroup(target) {
    target.traverse(o => { o.geometry?.dispose(); if (o.material) o.material.dispose(); if (o.element) o.element.remove(); });
    target.clear();
  }
  function removeObjects(target,predicate){for(const object of [...target.children])if(predicate(object)){target.remove(object);object.traverse(o=>{o.geometry?.dispose();if(o.material)o.material.dispose();if(o.element)o.element.remove();});}}
  function recordTiming(value){diagnostics.push(value);if(diagnostics.length>16)diagnostics.shift();container.dispatchEvent(new CustomEvent('pmc-viewer-timing',{detail:value}));}
  function navigationState(){
    const direction=camera.position.clone().sub(controls.target).normalize();
    const named=Object.keys({...VIEW_DIRECTIONS,...CORNER_VIEWS}).find(key=>direction.dot(viewDirection(key))>.99999)||null;
    return {projection:camera.isOrthographicCamera?'orthographic':'perspective',direction:direction.toArray(),view:named,target:controls.target.toArray()};
  }
  function setView(view){
    const direction=viewDirection(view);if(!direction||drag)return false;
    const distance=Math.max(camera.position.distanceTo(controls.target),1);
    camera.position.copy(controls.target).addScaledVector(direction,distance);
    controls.update();return true;
  }
  function projection(value){
    if(value===undefined)return camera.isOrthographicCamera?'orthographic':'perspective';
    if(!['perspective','orthographic'].includes(value)||drag)return false;
    if(projection()===value)return true;
    const target=controls.target.clone(),direction=camera.position.clone().sub(target);
    const distance=Math.max(direction.length(),1);direction.normalize();
    const span=cameraSpan(camera,distance);
    if(value==='orthographic'){
      orthoSpan=span;orthographic.zoom=1;
      orthographic.position.copy(target).addScaledVector(direction,distance);
      camera=orthographic;
    }else{
      perspective.zoom=1;
      const newDistance=span/(2*Math.tan(THREE.MathUtils.degToRad(perspective.fov/2)));
      perspective.position.copy(target).addScaledVector(direction,Math.max(newDistance,1));
      camera=perspective;
    }
    resizeViewport();controls.object=camera;controls.update();onViewChange(navigationState());
    return true;
  }
  function fit(view) {
    if (!block) return;
    if (!resizeViewport()) { pendingFit=view; return; }
    pendingFit=null;
    if(view)setView(view);
    frame(new THREE.Box3(new THREE.Vector3(0,0,0),new THREE.Vector3(block.length,block.width,block.height)));
  }
  function localBounds(id){
    if(id==='block'&&block)return new THREE.Box3(new THREE.Vector3(),new THREE.Vector3(block.length,block.width,block.height));
    if(displayContext?.nets?.some(net=>net.id===id)){
      const box=new THREE.Box3();
      for(const feature of displayContext.features||[])if(!feature.suppressed&&(feature.circuit===id||feature.route_net===id||feature.frozen_net===id||Object.values(feature.interface_nets||{}).includes(id)))box.union(localBounds(feature.id));
      return box;
    }
    const known=displayContext?.features?.find(feature=>feature.id===id);
    if(known?.suppressed)return new THREE.Box3();
    if(frameBoundsCache.has(id))return frameBoundsCache.get(id).clone();
    const owned=[...dragGroup.children,...group.children].filter(o=>o.isMesh&&(o.userData.owner===id||o.userData.id===id)&&(!dragOwners.has(o.userData.owner)||o.parent===dragGroup));
    const box=new THREE.Box3();for(const object of owned){object.updateMatrixWorld(true);box.union(new THREE.Box3().setFromObject(object));}
    if(box.isEmpty()&&displayContext?.features?.some(f=>f.id===id&&!f.suppressed)){
      try{for(const part of parameterModel(displayContext,new Set([id]),false).parts){
        const positions=part.vertices;for(let i=0;i<positions.length;i+=3)box.expandByPoint(new THREE.Vector3(positions[i],positions[i+1],positions[i+2]));
      }}catch{/* A missing display definition is not a framing measurement. */}
    }
    if(!box.isEmpty())frameBoundsCache.set(id,box.clone());
    return box;
  }
  function frame(idsOrBounds,{padding=1.12}={}){
    if(!block||drag)return {ok:false,reason:'Model navigation is unavailable during dragging.'};
    const box=new THREE.Box3(),missing=[];
    const targets=Array.isArray(idsOrBounds)?idsOrBounds:[idsOrBounds];
    for(const target of targets){
      let next;
      if(target?.isBox3)next=target;
      else if(target&&Array.isArray(target.min)&&Array.isArray(target.max))next=new THREE.Box3(new THREE.Vector3(...target.min),new THREE.Vector3(...target.max));
      else if(typeof target==='string')next=localBounds(target);
      if(next&&!next.isEmpty()&&[...next.min.toArray(),...next.max.toArray()].every(Number.isFinite))box.union(next);
      else missing.push(target);
    }
    if(box.isEmpty())return {ok:false,reason:'No displayed geometry is available for this target.',missing};
    if(clipping.enabled){
      const corners=[];for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z])corners.push(new THREE.Vector3(x,y,z));
      if(corners.every(point=>!clipAllows(point)))return {ok:false,reason:'The target is fully outside the active section plane.',missing};
    }
    if(!resizeViewport())return {ok:false,reason:'The viewport is not measurable.',missing};
    const span=frameCamera(camera,controls,box,container.clientWidth,container.clientHeight,padding);
    if(span!==null)orthoSpan=span;
    return {ok:true,missing};
  }
  function focus(id){return frame([id]);}
  function project(point){
    if(!Array.isArray(point)||point.length!==3||container.clientWidth<=0||container.clientHeight<=0)return null;
    camera.updateMatrixWorld();
    const projected=new THREE.Vector3(...point).project(camera),rect=renderer.domElement.getBoundingClientRect();
    return {x:rect.left+(projected.x+1)*rect.width/2,y:rect.top+(1-projected.y)*rect.height/2};
  }
  function clipAllows(point){return !clipping.enabled||clipPlane.distanceToPoint(point)>=-.001;}
  function updateClipMaterials(){
    for(const root of [group,dragGroup,handles,hitAreas,boundaryGroup,guides])root.traverse(o=>{
      if(!o.material)return;
      for(const material of Array.isArray(o.material)?o.material:[o.material])clipMaterial(material);
    });
  }
  function setClipping(next){
    if(drag)return false;
    if(!next?.enabled){clipping={enabled:false,axis:'x',position:0,keep:'gte'};}
    else {
      const axis=['x','y','z'].includes(next.axis)?next.axis:'x',size=block?.[{x:'length',y:'width',z:'height'}[axis]]||0;
      clipping={enabled:true,axis,position:Math.min(size,Math.max(0,Number(next.position)||0)),keep:next.keep==='lte'?'lte':'gte'};
      const sign=clipping.keep==='gte'?1:-1;
      clipPlane.normal.set(axis==='x'?sign:0,axis==='y'?sign:0,axis==='z'?sign:0);
      clipPlane.constant=-sign*clipping.position;
    }
    updateClipMaterials();updateVisibility();return true;
  }
  function resetClipping(){return setClipping({enabled:false});}
  function isolate(id,{includeRoutes=false,stockContext=true}={}){
    if(!displayContext?.features?.some(f=>f.id===id&&!f.suppressed))return {ok:false,reason:'The feature is not available in the displayed model.'};
    if(machinedBody&&!([...group.children,...dragGroup.children].some(o=>o.isMesh&&o.userData.owner===id)))return {ok:false,reason:'Owner machining geometry is not loaded. Open Feature layers and retry.'};
    isolation={kind:'feature',id,includeRoutes,stockContext};updateVisibility();return {ok:true};
  }
  function isolateContact(netPair=null){isolation={kind:'contact',netPair};updateVisibility();return true;}
  function clearIsolation(){if(!isolation)return false;isolation=null;updateVisibility();return true;}
  function resetTransient(){
    isolation=null;pendingFit=null;selected='block';secondary.clear();issueRows=[];disposeGroup(markerGroup);disposeGroup(localGizmo);hover(null);resetClipping();select(selected);updateVisibility();
  }
  function updateVisibility() {
    const owners=new Set();
    if(isolation?.kind==='feature'){
      owners.add(isolation.id);
      if(isolation.includeRoutes){
        const origin=displayContext?.features?.find(f=>f.id===isolation.id);
        const nets=new Set([origin?.circuit,origin?.route_net,origin?.frozen_net,...Object.values(origin?.interface_nets||{})].filter(Boolean));
        for(const f of displayContext?.features||[])if((f.route_net||f.frozen_net)&&nets.has(f.route_net||f.frozen_net))owners.add(f.id);
      }
    }
    const ownLayer=p=>!(['zone','zone-edge'].includes(p.kind)&&!visible.zones)
      &&!(p.kind==='plug'&&!visible.closures);
    const contactMatches=p=>p.kind==='collision'&&(!isolation.netPair||p.nets?.length===2&&isolation.netPair.every(net=>p.nets.includes(net)));
    group.children.forEach(o => {
      const p=o.userData, exact=machinedBody;
      if(!exact) o.visible=(!p.circuit||visible.circuits.has(p.circuit))&&(!['drilling','plug'].includes(p.kind)||visible.drillings)&&(!['cavity','cavity-edge'].includes(p.kind)||visible.cavities)&&(!['zone','zone-edge'].includes(p.kind)||visible.zones);
      else o.visible = mode==='solid' ? ['body','edge','collision'].includes(p.kind)||xray&&p.kind==='hydraulic-net'&&visible.circuits.has(p.circuit) :
        mode==='void' ? ['machined-void','collision'].includes(p.kind) :
        mode==='features' ? (['cavity','cavity-edge'].includes(p.kind)&&visible.cavities || p.kind==='port-machining'&&visible.ports || ['zone','zone-edge','port'].includes(p.kind)&&visible.zones || ['drilling-machining','mounting-machining'].includes(p.kind)&&visible.drillings || p.kind==='plug'&&visible.closures || p.kind==='collision') :
        ['body','edge','collision'].includes(p.kind)||p.kind==='hydraulic-net'&&visible.drillings&&visible.circuits.has(p.circuit);
      if(isolation?.kind==='contact')o.visible=contactMatches(p);
      else if(isolation?.kind==='feature')o.visible=p.kind==='body'?isolation.stockContext!==false:owners.has(p.owner)&&ownLayer(p);
      if(p.kind==='body'){const alpha=isolation?.kind==='feature' ? .08 : mode==='solid' ? 1 : opacity;o.visible=o.visible&&alpha>0;o.material.opacity=alpha;o.material.transparent=alpha<1;o.material.depthWrite=alpha>=.99;o.material.depthTest=true;}
      else if(o.isMesh){o.material.depthTest=!xray;o.material.depthWrite=!xray;o.material.transparent=xray||['cavity','zone'].includes(p.kind);o.material.opacity=xray?.65:['cavity','zone'].includes(p.kind)?.38:1;}
      if(p.kind==='edge'&&mode==='review'&&opacity===0)o.visible=false;
      if(p.kind==='collision'){o.material.depthTest=true;o.material.depthWrite=true;o.renderOrder=12;}
      if(dragOwners.has(p.owner))o.visible=false;
    });
    dragGroup.children.forEach(o=>{const p=o.userData;o.visible=(!p.circuit||visible.circuits.has(p.circuit))&&(!['drilling','plug'].includes(p.kind)||visible.drillings)&&(!['cavity','cavity-edge'].includes(p.kind)||visible.cavities)&&(!['zone','zone-edge'].includes(p.kind)||visible.zones);if(isolation)o.visible=isolation.kind==='feature'&&owners.has(p.owner)&&ownLayer(p);if(o.isMesh){o.material.depthTest=!xray;o.material.depthWrite=!xray;o.material.transparent=true;o.material.opacity=.72;}});
    container.dataset.xray=String(xray);container.dataset.viewMode=mode;const stock=group.children.find(o=>o.userData.kind==='body');container.dataset.stockVisible=String(!!stock?.visible);container.dataset.stockOpacity=String(stock?.material.opacity??opacity);
    handles.children.forEach(o=>{const p=o.userData;o.visible=(p.kind!=='drilling'||visible.drillings)&&(!p.circuit||visible.circuits.has(p.circuit));if(isolation)o.visible=isolation.kind==='feature'&&owners.has(p.owner);if(clipping.enabled&&!clipAllows(o.position))o.visible=false;});
    hitAreas.children.forEach(o=>{o.visible=editing&&(!isolation||isolation.kind==='feature'&&owners.has(o.userData.owner))&&clipAllows(o.position);});
    boundaryGroup.children.forEach(o=>{o.visible=!isolation||isolation.kind==='feature'&&owners.has(o.userData.owner);});
    markerGroup.children.forEach(o=>{o.userData.displayEnabled=(!isolation||isolation.kind==='feature'&&owners.has(o.userData.id))&&clipAllows(o.position);o.visible=o.userData.displayEnabled;});
    labelGroup.children.forEach(o => {
      const p = o.userData;
      o.visible = visible.labels && (p.kind !== 'cavity' || visible.cavities) && (p.kind !== 'drilling' || visible.drillings)
        && (!p.circuit || visible.circuits.has(p.circuit));
      if(isolation)o.visible=o.visible&&isolation.kind==='feature'&&owners.has(p.id);
      if(clipping.enabled&&!clipAllows(o.position))o.visible=false;
      o.userData.displayEnabled=o.visible;
    });
    for(const label of reference.children)if(label.isCSS2DObject)label.visible=!isolation&&clipAllows(label.position);
    localGizmo.visible=!!localGizmo.userData.featureId&&(!isolation||isolation.kind==='feature'&&isolation.id===localGizmo.userData.featureId)&&clipAllows(localGizmo.position);
    collisionButton.textContent=isolation?.kind==='contact'?'Show networks':'Isolate exact contact';
    container.dataset.isolation=isolation?.kind||'none';
    container.dataset.clipping=clipping.enabled?`${clipping.axis}:${clipping.keep}:${clipping.position}`:'off';
  }
  function layoutLabels(){
    const width=container.clientWidth,height=container.clientHeight;
    if(width<=0||height<=0)return;
    const boxes=[];
    const intersects=box=>boxes.some(other=>box.x<other.x+other.w&&box.x+box.w>other.x&&box.y<other.y+other.h&&box.y+box.h>other.y);
    const place=(object,w,h,priority=false)=>{
      if(!object.userData.displayEnabled){object.visible=false;return;}
      const p=object.position.clone().project(camera);
      if(p.z<-1||p.z>1){object.visible=false;return;}
      const box={x:(p.x*.5+.5)*width-w/2,y:(-.5*p.y+.5)*height-h/2,w,h};
      if(!priority&&intersects(box)){object.visible=false;return;}
      object.visible=true;boxes.push(box);
    };
    for(const object of markerGroup.children)place(object,26,26,true);
    const selectedLabel=labelGroup.children.find(object=>object.userData.id===selected);
    if(selectedLabel)place(selectedLabel,selectedLabel.userData.displayWidth,20,true);
    for(const object of labelGroup.children){
      if(object===selectedLabel)continue;
      place(object,object.userData.displayWidth,20);
    }
  }
  function select(id) {
    selected = id;
    [...group.children,...dragGroup.children].forEach(o => {
      if (o.material?.emissive) {const own=o.userData.owner,net=group.children.find(x=>x.userData.owner===id)?.userData.circuit;o.material.emissive.set(own===id&&id!=='block'?'#b5a32b':secondary.has(own)?'#a34b67':own===hovered?'#507c74':net&&o.userData.circuit===net?'#1d332b':'#000000');}
    });
    for(const h of handles.children){h.material.color.set(h.userData.owner === hovered ? '#ffffff' : h.userData.owner === id ? '#a7e7c0' : '#65e4b1');h.scale.setScalar(h.userData.owner === hovered?1.25:1);}
    updateLocalGizmo();
  }
  function updateLocalGizmo(){
    disposeGroup(localGizmo);localGizmo.userData.featureId=null;container.dataset.localGizmo='none';
    if(!block||selected==='block'||design?.features?.find(f=>f.id===selected)?.suppressed)return;
    const current=dragOwners.has(selected)?design:displayContext;
    const feature=current?.features?.find(f=>f.id===selected&&!f.suppressed);
    if(!feature||!axes[feature.face])return;
    const placement=current===displayContext?displayPlacements?.[selected]||pose(feature,current.block):pose(feature,current.block);
    if(!placement?.origin||!placement.origin.every(Number.isFinite))return;
    const [u,v]=axes[feature.face],angle=(feature.rotation||0)*Math.PI/180;
    const eu=new THREE.Vector3(),ev=new THREE.Vector3();eu.setComponent(u,1);ev.setComponent(v,1);
    const directions=[eu.clone().multiplyScalar(Math.cos(angle)).addScaledVector(ev,Math.sin(angle)),
      ev.clone().multiplyScalar(Math.cos(angle)).addScaledVector(eu,-Math.sin(angle)),
      new THREE.Vector3(...placement.direction).normalize()];
    if(directions.some(direction=>!direction.toArray().every(Number.isFinite)||direction.lengthSq()<.5))return;
    const length=Math.min(18,Math.max(9,Math.min(block.length,block.width,block.height)*.13));
    localGizmo.position.set(...placement.origin);
    for(const [index,direction] of directions.entries()){
      const color=[0xff6970,0x73d78b,0x72a8ff][index];
      const arrow=new THREE.ArrowHelper(direction,new THREE.Vector3(),length,color,length*.24,length*.12);
      arrow.traverse(object=>{if(object.material){object.material.depthTest=false;object.material.depthWrite=false;}object.renderOrder=18;});
      localGizmo.add(arrow);
      const badge=document.createElement('span');badge.className='local-gizmo-label';badge.textContent=['U','V','IN'][index];badge.setAttribute('aria-hidden','true');
      const label=new CSS2DObject(badge);label.position.copy(direction).multiplyScalar(length+3);localGizmo.add(label);
    }
    localGizmo.userData.featureId=selected;container.dataset.localGizmo=selected;
    localGizmo.visible=(!isolation||isolation.kind==='feature'&&isolation.id===selected)&&clipAllows(localGizmo.position);
  }
  function materializePart(p,target,metrics){
    let started=performance.now();const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(p.vertices, 3));geo.setIndex(p.triangles);
    metrics.geometry_ms+=performance.now()-started;started=performance.now();geo.computeVertexNormals();metrics.normals_ms+=performance.now()-started;
    const transparent = ['body','cavity','zone'].includes(p.kind);
    const material = clipMaterial(new THREE.MeshStandardMaterial({ color: p.color, metalness: p.kind === 'body' ? .35 : .12,
      roughness: .6, transparent, opacity: p.kind==='body'?opacity:p.kind==='cavity'?.38:p.kind==='zone'?.1:1,
      depthWrite: !transparent, side: THREE.DoubleSide }));
    const object = new THREE.Mesh(geo, material); object.userData = p;
    object.renderOrder = p.kind === 'body' ? 3 : p.kind === 'cavity' ? 2 : 0;target.add(object);
    if (['body','cavity','zone'].includes(p.kind)) {
      started=performance.now();const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), clipMaterial(new THREE.LineBasicMaterial({ color:p.kind==='body'?'#8197ad':p.kind==='cavity'?'#e1edf5':p.color, transparent:true,opacity:p.kind==='body'?.45:p.kind==='cavity'?.95:.65 })));
      metrics.edges_ms+=performance.now()-started;edges.userData={...p,kind:p.kind==='body'?'edge':p.kind+'-edge'};edges.renderOrder=4;target.add(edges);
    }
  }
  function setSecondary(ids){secondary=new Set(ids||[]);select(selected);}
  function setIssueMarkers(rows){
    issueRows=rows||[];disposeGroup(markerGroup);
    for(const row of issueRows){
      const feature=displayContext?.features?.find(f=>f.id===row.id&&!f.suppressed);
      if(!feature)continue;
      const placement=displayPlacements?.[row.id]||pose(feature,displayContext.block);
      if(!placement?.origin)continue;
      const button=document.createElement('button');button.type='button';button.className='issue-marker';
      button.textContent=String((row.FAIL||0)+(row.WARNING||0));
      button.dataset.severity=row.FAIL?'FAIL':'WARNING';
      button.setAttribute('aria-label',`Affected feature reference: ${featureLabel(feature,displayContext)}; ${row.FAIL||0} failures and ${row.WARNING||0} warnings`);
      button.title='Affected feature reference, not an exact failure point';
      button.onclick=event=>{event.stopPropagation();onMarkerSelect(row.id);};
      const marker=new CSS2DObject(button);marker.position.set(...placement.origin).addScaledVector(new THREE.Vector3(...(placement.direction||[0,0,1])),5);marker.userData={id:row.id};markerGroup.add(marker);
    }
    updateVisibility();
  }
  function addLabel(f,context,placement){
    if(!placement)return;
    const features=context.features;
    if (f.kind === 'drilling' && !f.plugged && features.some(p => p.kind === 'port' && p.face === f.face && p.u === f.u && p.v === f.v)) return;
    const element = document.createElement('div'); element.className = 'model-label'; element.textContent = featureLabel(f,context);
    const label = new CSS2DObject(element); label.position.set(...placement.origin).addScaledVector(new THREE.Vector3(...placement.direction), -8);
    label.userData = {...f,displayWidth:Math.min(170,Math.max(44,element.textContent.length*6+14))}; labelGroup.add(label);
  }
  function load(model, value) {
    const loadStarted=performance.now(),metrics={kind:'exact-load',geometry_ms:0,normals_ms:0,edges_ms:0,labels_ms:0};
    const context=Array.isArray(value)?{...(design||{}),features:value}:value,features=context.features;design=context;displayContext=context;displayPlacements=model.placements||{};frameBoundsCache.clear();
    dragOwners.clear();
    renderedFeatures=features.map(f=>({...f}));
    references.load(model.geometry_kind,features);const first = !block; block = model.block;machinedBody=model.geometry_kind!=='parameter-preview';container.dataset.geometry=machinedBody?'machined-brep':'parameter-preview';
    deferredLayers=new Set(model.deferred_layers||[]);loadedLayers=new Set(model.loaded_layers||[]);container.dataset.deferredLayers=[...deferredLayers].join(',');container.dataset.loadedLayers=[...loadedLayers].join(',');
    if(isolation?.kind==='feature'&&!features.some(f=>f.id===isolation.id&&!f.suppressed))isolation=null;
    collisionNotice.hidden=!(machinedBody&&model.collisions?.length);
    collisionText.textContent=(model.collisions||[]).map(c=>`INVALID CROSS-NET CONTACT · ${c.nets.join(' ↔ ')} · ${c.volume_mm3.toFixed(2)} mm³`).join('; ');
    disposeGroup(reference);reference.add(new THREE.AxesHelper(Math.min(block.length,block.width,block.height)*.35));
    for(const [text,p]of [['0,0,0',[0,0,0]],['+X',[block.length*.4,0,0]],['+Y',[0,block.width*.4,0]],['+Z',[0,0,block.height*.4]]]){const e=document.createElement('div');e.className='model-label';e.textContent=text;const l=new CSS2DObject(e);l.position.set(...p);reference.add(l);}
    disposeGroup(group); disposeGroup(labelGroup);disposeGroup(dragGroup);
    if (grid) { scene.remove(grid); grid.geometry.dispose(); grid.material.dispose(); }
    grid = new THREE.GridHelper(Math.max(block.length, block.width) * 2.8, 28, 0x3d5266, 0x2a394b);
    grid.rotation.x = Math.PI / 2; grid.position.set(block.length / 2, block.width / 2, -.5); scene.add(grid);
    for (const p of model.parts) {
      if (p.circuit && !knownCircuits.has(p.circuit)) { knownCircuits.add(p.circuit); visible.circuits.add(p.circuit); }
      materializePart(p,group,metrics);
    }
    let labelsStarted=performance.now();
    for (const f of features) {
      const pose = model.placements[f.id]; if (!pose) continue;
      addLabel(f,context,pose);
    }
    metrics.labels_ms=performance.now()-labelsStarted;metrics.load_ms=performance.now()-loadStarted;
    if(clipping.enabled)setClipping(clipping);else updateVisibility();setIssueMarkers(issueRows);select(selected); if (first) fit();
    requestAnimationFrame(()=>{metrics.first_frame_ms=performance.now()-loadStarted;recordTiming(Object.fromEntries(Object.entries(metrics).map(([k,v])=>[k,typeof v==='number'?Math.round(v*100)/100:v])));});
  }
  function loadLayer(layer,parts){
    const started=performance.now(),metrics={kind:'exact-layer',layer,geometry_ms:0,normals_ms:0,edges_ms:0,labels_ms:0};
    removeObjects(group,o=>o.userData.layer===layer);frameBoundsCache.clear();
    for(const raw of parts){const p={...raw,layer};if(p.circuit&&!knownCircuits.has(p.circuit)){knownCircuits.add(p.circuit);visible.circuits.add(p.circuit);}materializePart(p,group,metrics);}
    deferredLayers.delete(layer);loadedLayers.add(layer);container.dataset.deferredLayers=[...deferredLayers].join(',');container.dataset.loadedLayers=[...loadedLayers].join(',');metrics.load_ms=performance.now()-started;updateVisibility();select(selected);
    requestAnimationFrame(()=>{metrics.first_frame_ms=performance.now()-started;recordTiming(Object.fromEntries(Object.entries(metrics).map(([k,v])=>[k,typeof v==='number'?Math.round(v*100)/100:v])));});
  }
  const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
  const knownCircuits = new Set(visible.circuits);
  function aim(e) {const rect=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);ray.setFromCamera(pointer,camera);}
  function addBoundaries(f){
    const definitionId=f.cavity_id||f.port_definition_id;if(!definitionId||f.suppressed)return;const def=design.library.find(d=>d.id===definitionId),p=pose(f,design.block),[u,v]=axes[f.face],angle=(f.rotation||0)*Math.PI/180;
    for(const boundary of def?.boundaries||[])for(const height of boundary.height?[0,boundary.height]:[0]){const outline=boundary.circle?Array.from({length:64},(_,i)=>[boundary.circle[0]+boundary.circle[2]*Math.cos(i*Math.PI/32),boundary.circle[1]+boundary.circle[2]*Math.sin(i*Math.PI/32)]):boundary.points;const points=outline.map(([x,y])=>{const q=p.origin.map((a,i)=>a-p.direction[i]*(height+.2));q[u]+=x*Math.cos(angle)-y*Math.sin(angle);q[v]+=x*Math.sin(angle)+y*Math.cos(angle);return new THREE.Vector3(...q);});points.push(points[0].clone());const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),clipMaterial(new THREE.LineBasicMaterial({color:boundary.category==='mounting-footprint'?'#f2d454':'#be8aee',depthTest:false})));line.userData={owner:f.id};line.renderOrder=9;boundaryGroup.add(line);}
  }
  function addControl(f){
    if(f.suppressed||(f.kind==='drilling'&&!f.frozen_net)||f.parent_id)return;const p=pose(f,design.block),d=new THREE.Vector3(...p.direction);
    const h=new THREE.Mesh(new THREE.RingGeometry(4,6,32),clipMaterial(new THREE.MeshBasicMaterial({color:f.id===selected?0xffffff:0x65e4b1,side:THREE.DoubleSide,depthTest:false})));
    h.position.set(...p.origin).addScaledVector(d,f.kind==='drilling'?f.depth/2:-.3);h.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),d);h.userData={owner:f.id,kind:f.kind,circuit:f.circuit};h.renderOrder=10;handles.add(h);
    const definitionId=f.cavity_id||f.port_definition_id,def=design.library?.find(x=>x.id===definitionId),target=new THREE.Mesh(f.kind==='drilling'?new THREE.CylinderGeometry(1,1,f.depth,24):new THREE.CircleGeometry(1,32),clipMaterial(new THREE.MeshBasicMaterial({side:THREE.DoubleSide,transparent:true,opacity:0,depthWrite:false,colorWrite:false})));
    target.position.copy(h.position);target.quaternion.copy(h.quaternion);if(f.kind==='drilling')target.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d);
    const threadDiameter=f.thread_definition_id?design.threads?.find(row=>row.id===f.thread_definition_id)?.tap_diameter_mm:null;
    target.userData={owner:f.id,kind:f.kind,inward:d,mouthRadius:def?Math.max(...def.stages.map(s=>s.diameter))/2:(threadDiameter||f.diameter)/2};hitAreas.add(target);
  }
  function setDesign(value) {
    design=value;disposeGroup(handles);disposeGroup(hitAreas);disposeGroup(boundaryGroup);
    for(const f of design.features){addBoundaries(f);addControl(f);}
    select(selected);updateVisibility();
  }
  function hitTarget(){
    const viewDirection=camera.position.clone().sub(controls.target).normalize();
    const targets=hitAreas.children.filter(h=>editing&&h.visible&&(h.userData.kind!=='cavity'||visible.cavities)&&(h.userData.kind!=='drilling'||visible.drillings&&visible.circuits.has(design.features.find(f=>f.id===h.userData.owner)?.circuit))&&(h.userData.kind==='drilling'||(camera.isOrthographicCamera?viewDirection:camera.position.clone().sub(h.position)).dot(h.userData.inward)<0));
    for(const h of targets){const mmPerPixel=camera.isOrthographicCamera?(camera.top-camera.bottom)/camera.zoom/Math.max(1,container.clientHeight):2*camera.position.distanceTo(h.position)*Math.tan(THREE.MathUtils.degToRad(camera.fov/2))/Math.max(1,container.clientHeight)/camera.zoom,r=Math.max(h.userData.mouthRadius+6*mmPerPixel,12*mmPerPixel);if(h.userData.kind==='drilling')h.scale.set(r,1,r);else h.scale.setScalar(r);h.updateMatrixWorld();}
    return ray.intersectObjects(targets).find(hit=>clipAllows(hit.point));
  }
  function hover(id){if(hovered===id)return;hovered=id;renderer.domElement.style.cursor=id?'grab':'';renderer.domElement.title=id?`Drag ${id} on its face`:'';container.dataset.hoveredFeature=id||'';select(selected);onHover(id);}
  function parameterModel(value,onlyIds=null,includeBlock=true) {
    const parts=[], placements={};
    const add=(geo,p,color,kind,id,owner,circuit)=>{geo.applyQuaternion(p.q);geo.translate(...p.center);parts.push({vertices:Array.from(geo.attributes.position.array),triangles:geo.index?Array.from(geo.index.array):Array.from({length:geo.attributes.position.count},(_,i)=>i),color,kind,id,owner,circuit});geo.dispose();};
    const b=value.block;if(includeBlock)add(new THREE.BoxGeometry(b.length,b.width,b.height),{q:new THREE.Quaternion(),center:[b.length/2,b.width/2,b.height/2]},'#9ba9b9','body','block');
    const cylinder=(f,diam,start,end,color,kind,id,options={})=>{const p=pose(f,b),d=new THREE.Vector3(...p.direction),a=(f.rotation||0)*Math.PI/180,[u,v]=axes[f.face];p.origin[u]+=(options.offset_u||0)*Math.cos(a)-(options.offset_v||0)*Math.sin(a);p.origin[v]+=(options.offset_u||0)*Math.sin(a)+(options.offset_v||0)*Math.cos(a);add(new THREE.CylinderGeometry((options.kind==='cone'?options.end_diameter:diam)/2,diam/2,end-start,32),{q:new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),d),center:p.origin.map((a,i)=>a+p.direction[i]*(start+end)/2)},color,kind,id,f.id,f.circuit);};
    for(const f of value.features.filter(f=>!f.suppressed&&(!onlyIds||onlyIds.has(f.id)))) {placements[f.id]=pose(f,b);const definitionId=f.cavity_id||f.port_definition_id;if(definitionId){const d=value.library.find(d=>d.id===definitionId);for(const [i,s] of (d.cutting_primitives?.length?d.cutting_primitives:d.stages).entries())cylinder(f,s.diameter,s.start,s.end,f.kind==='port'?(value.nets.find(n=>n.id===f.circuit)?.color||'#9cc8e8'):'#b4c7da',f.kind==='port'?'port':'cavity',f.id+'-'+i,s);for(const z of f.kind==='port'?[]:d.zones){const netId=f.interface_nets[z.id],net=value.nets.find(n=>n.id===netId);cylinder(f,z.diameter,z.start,z.end,net?.color||({P:'#ef5959',T:'#459cff',A:'#41ca8b',B:'#f2d454'}[netId])||'#b08bea','zone',f.id+':'+z.id,z);}}else{const diameter=f.thread_definition_id?value.threads?.find(row=>row.id===f.thread_definition_id)?.tap_diameter_mm:f.diameter;if(!diameter)throw Error(`${f.id}: thread machining definition is not loaded`);cylinder(f,diameter,0,f.depth,value.nets.find(n=>n.id===f.circuit)?.color||({P:'#ef5959',T:'#459cff',A:'#41ca8b',B:'#f2d454'}[f.circuit])||'#b08bea',f.kind,f.id);const tip=f.tip_angle===180?0:diameter/2/Math.tan((f.tip_angle??118)*Math.PI/360);if(tip)cylinder(f,diameter,f.depth,f.depth+tip,value.nets.find(n=>n.id===f.circuit)?.color||'#b08bea',f.kind,f.id+':tip',{kind:'cone',end_diameter:0});if(f.plugged)cylinder(f,diameter,0,f.plug_length,'#d5dee9','plug',f.id+':plug');}}
    return {block:b,parts,placements,geometry_kind:'parameter-preview'};
  }
  function preview(value) {load(parameterModel(value),value);}
  function updateFeature(value,id){
    const started=performance.now(),source=value.features.find(item=>item.id===id);if(!source)return;
    const affected=new Set([id]);let changed=true;while(changed){changed=false;for(const f of value.features)if(f.parent_id&&affected.has(f.parent_id)&&!affected.has(f.id)){affected.add(f.id);changed=true;}}
    const features=value.features.map(f=>({...f,local_offset:[...(f.local_offset||[0,0])]})),byId=new Map(features.map(f=>[f.id,f]));
    const resolved=new Set();function resolveAttached(f){if(resolved.has(f.id))return;if(f.parent_id){const parent=byId.get(f.parent_id);resolveAttached(parent);const angle=(parent.rotation||0)*Math.PI/180,[u,v]=f.local_offset;f.face=parent.face;f.u=parent.u+u*Math.cos(angle)-v*Math.sin(angle);f.v=parent.v+u*Math.sin(angle)+v*Math.cos(angle);f.suppressed=f.suppressed||parent.suppressed;}resolved.add(f.id);}for(const key of affected)resolveAttached(byId.get(key));
    const current={...value,features,library:value.library};design=current;displayContext=current;dragOwners=affected;disposeGroup(dragGroup);for(const key of affected)frameBoundsCache.delete(key);
    const metrics={kind:'drag-update',feature_parts:0,elapsed_ms:0,unrelated_objects:group.children.length};
    const model=parameterModel(current,affected,false),build={geometry_ms:0,normals_ms:0,edges_ms:0,labels_ms:0};
    for(const raw of model.parts){materializePart({...raw,drag_preview:true},dragGroup,build);metrics.feature_parts++;}
    for(const key of affected){const f=byId.get(key);removeObjects(labelGroup,o=>o.userData.id===key);addLabel(f,current,model.placements[key]);removeObjects(handles,o=>o.userData.owner===key);removeObjects(hitAreas,o=>o.userData.owner===key);removeObjects(boundaryGroup,o=>o.userData.owner===key);addBoundaries(f);addControl(f);}
    metrics.elapsed_ms=Math.round((performance.now()-started)*100)/100;recordTiming(metrics);updateVisibility();select(selected);
  }
  let down, drag;
  renderer.domElement.addEventListener('pointerdown', e => {
    down=[e.clientX,e.clientY];if(e.button!==0||!design||!editing)return;aim(e);
    const hit=hitTarget();if(!hit)return;
    const f=design.features.find(f=>f.id===hit.object.userData.owner);if(f.parent_id)return;
    const p=pose(f,design.block),normal=new THREE.Vector3(...p.direction),plane=new THREE.Plane().setFromNormalAndCoplanarPoint(normal,new THREE.Vector3(...p.origin));
    const point=ray.ray.intersectPlane(plane,new THREE.Vector3());if(!point)return;
    drag={f,plane,start:point,u:f.u,v:f.v,moved:false,pointerId:e.pointerId};controls.enabled=false;renderer.domElement.setPointerCapture(e.pointerId);onSelect(f.id);hover(f.id);renderer.domElement.style.cursor='grabbing';container.classList.add('dragging');e.stopImmediatePropagation();
  },true);
  renderer.domElement.addEventListener('pointermove',e=>{
    aim(e);
    if(!drag){
      const h=hitTarget()||ray.intersectObjects(group.children.filter(o=>o.isMesh&&o.visible&&o.userData.kind==='drilling')).find(hit=>clipAllows(hit.point));
      hover(h?.object.userData.owner||null);return;
    }
    if(!drag.moved&&Math.hypot(e.clientX-down[0],e.clientY-down[1])<3)return;
    const point=ray.ray.intersectPlane(drag.plane,new THREE.Vector3());if(!point)return;
    const [u,v]=axes[drag.f.face],delta=point.clone().sub(drag.start).toArray();
    try{
      let [nu,nv]=clamp(drag.f,design,drag.u+delta[u],drag.v+delta[v],e.altKey?0:1);
      disposeGroup(guides);
      if(document.getElementById('smart-snap')?.checked&&!e.altKey){
        const aligned=smartAlign(drag.f,design,drag.u+delta[u],drag.v+delta[v],2,references.features);
        [nu,nv]=aligned.values;
        for(const g of aligned.guides){
          const p=pose({...drag.f,u:nu,v:nv},design.block).origin,a=[...p],b=[...p],other=g.axis===u?v:u;
          a[other]=0;b[other]=[design.block.length,design.block.width,design.block.height][other];guideLine(a,b,'#f2d454');
        }
        container.dataset.alignment=aligned.guides.map(g=>g.label).join(', ');
      }
      drag.moved=true;onDrag(drag.f.id,nu,nv,false);
    }catch{}
  });
  function finish(e,cancel=false){if(!drag)return false;const old=drag;drag=null;disposeGroup(guides);delete container.dataset.alignment;controls.enabled=true;container.classList.remove('dragging');renderer.domElement.style.cursor=hovered?'grab':'';if(renderer.domElement.hasPointerCapture(e.pointerId))renderer.domElement.releasePointerCapture(e.pointerId);if(old.moved)onDrag(old.f.id,cancel?old.u:design.features.find(f=>f.id===old.f.id).u,cancel?old.v:design.features.find(f=>f.id===old.f.id).v,true);return true;}
  function cancelInteraction(){return drag?finish({pointerId:drag.pointerId},true):false;}
  renderer.domElement.addEventListener('pointercancel',e=>finish(e,true));
  renderer.domElement.addEventListener('lostpointercapture',e=>finish(e,true));
  renderer.domElement.addEventListener('pointerleave',()=>{if(!drag)hover(null);});
  renderer.domElement.addEventListener('pointerup', e => {
    if(finish(e))return;
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4 || e.button !== 0) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set((e.clientX - rect.left) / rect.width * 2 - 1, -(e.clientY - rect.top) / rect.height * 2 + 1);
    ray.setFromCamera(pointer, camera);
    const candidates = group.children.filter(o => o.isMesh && o.visible && (mode === 'solid' || o.userData.kind !== 'body'));
    const hit = ray.intersectObjects(candidates.filter(o=>o.userData.kind==='drilling')).find(item=>clipAllows(item.point))||ray.intersectObjects(candidates).find(item=>clipAllows(item.point));
    onSelect(hit ? hit.object.userData.owner || 'block' : 'block');
  });
  function resizeViewport() {
    const w = container.clientWidth, h = container.clientHeight;
    if(w<=0||h<=0)return false;
    resizeCamera(camera,w,h,orthoSpan);renderer.setSize(w,h);labels.setSize(w,h);
    return true;
  }
  const resize = new ResizeObserver(() => {if(resizeViewport()&&pendingFit!==null)fit(pendingFit);});
  resize.observe(container);
  renderer.setAnimationLoop(() => { controls.update();layoutLabels();renderer.render(scene, camera);labels.render(scene, camera); });
  return { circuitVisible(id){return visible.circuits.has(id);}, displayBlock(){return block?{...block}:null;}, inspection(){return {geometry:machinedBody?'machined-brep':'parameter-preview',mode,xray,opacity,projection:projection(),isolation,clipping:{...clipping},localGizmo:{id:localGizmo.userData.featureId||null,visible:localGizmo.visible,origin:localGizmo.position.toArray()},camera:camera.position.toArray(),target:controls.target.toArray(),deferredLayers:[...deferredLayers],loadedLayers:[...loadedLayers],diagnostics:[...diagnostics],parts:[...group.children,...dragGroup.children].filter(o=>o.isMesh).map(o=>({id:o.userData.id,kind:o.userData.kind,owner:o.userData.owner,dragPreview:!!o.userData.drag_preview,visible:o.visible,depthTest:o.material.depthTest,depthWrite:o.material.depthWrite,opacity:o.material.opacity,positions:Array.from(o.geometry.attributes.position.array)}))};}, load,loadLayer,needsLayer(layer){return deferredLayers.has(layer)&&!loadedLayers.has(layer);},updateFeature,fit,frame,focus,project,setView,projection,navigationState,isolate,isolateContact,clearIsolation,setClipping,resetClipping,resetTransient,cancelInteraction,setSecondary,setIssueMarkers,hover,select,setDesign,preview,setReferences(value){references.reset(value);}, editing(value){editing=value;handles.visible=value;updateVisibility();},xray(value) { xray=value;updateVisibility(); }, mode(value) { mode = value; if(isolation)clearIsolation();updateVisibility(); }, opacity(value) { opacity = value; updateVisibility(); },
    toggle(key, value) { visible[key] = value; updateVisibility(); }, circuit(id, show) { show ? visible.circuits.add(id) : visible.circuits.delete(id); updateVisibility(); } };
}
