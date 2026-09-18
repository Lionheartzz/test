import {createReferenceState} from './viewer-references.js';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { axes, pose, clamp, smartAlign, featureLabel } from './kinematics.js';

export function createViewer(container, onSelect, onDrag = ()=>{}) {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, .1, 10000);
  camera.up.set(0, 0, 1);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
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
  let collisionFocus=false;
  collisionButton.onclick=()=>{collisionFocus=!collisionFocus;collisionButton.textContent=collisionFocus?'Show networks':'Isolate exact contact';updateVisibility();};
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  scene.add(new THREE.HemisphereLight(0xe8f4ff, 0x526478, 2.6));
  for (const [position, intensity] of [[[100, -200, 400], 3], [[-200, 200, 180], 1.8]]) {
    const light = new THREE.DirectionalLight(0xffffff, intensity);
    light.position.set(...position); scene.add(light);
  }
  let group = new THREE.Group(), labelGroup = new THREE.Group(), dragGroup=new THREE.Group(), grid;
  scene.add(group, labelGroup,dragGroup);
  const reference=new THREE.Group(),guides=new THREE.Group();scene.add(reference,guides);
  function guideLine(a,b,color){const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a),new THREE.Vector3(...b)]),new THREE.LineBasicMaterial({color,depthTest:false}));line.renderOrder=20;guides.add(line);}

  let block, mode = 'review', opacity = .22, xray = false, selected = 'block', machinedBody=false, pendingFit=null;
  let deferredLayers=new Set(),loadedLayers=new Set(),dragOwners=new Set();const diagnostics=[];
  const references=createReferenceState();
  let renderedFeatures=[], design, editing = true, handles = new THREE.Group(); scene.add(handles);
  const hitAreas = new THREE.Group(); scene.add(hitAreas);
  let hovered = null;const boundaryGroup=new THREE.Group();scene.add(boundaryGroup);
  const visible = { cavities: true, ports: true, closures: true, zones: true, drillings: true, labels: true, circuits: new Set(['P', 'T', 'A', 'B', 'LS', 'Drain']) };
  function disposeGroup(target) {
    target.traverse(o => { o.geometry?.dispose(); if (o.material) o.material.dispose(); if (o.element) o.element.remove(); });
    target.clear();
  }
  function removeObjects(target,predicate){for(const object of [...target.children])if(predicate(object)){target.remove(object);object.traverse(o=>{o.geometry?.dispose();if(o.material)o.material.dispose();if(o.element)o.element.remove();});}}
  function recordTiming(value){diagnostics.push(value);if(diagnostics.length>16)diagnostics.shift();container.dispatchEvent(new CustomEvent('pmc-viewer-timing',{detail:value}));}
  function fit(view = 'iso') {
    if (!block) return;
    if (!resizeViewport()) { pendingFit=view; return; }
    pendingFit=null;
    const center = new THREE.Vector3(block.length / 2, block.width / 2, block.height / 2);
    const radius = Math.hypot(block.length, block.width, block.height) / 2;
    const halfFov = Math.min(THREE.MathUtils.degToRad(camera.fov / 2), Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect));
    const distance = radius / Math.sin(halfFov) * 1.12;
    const directions={top:[0,-.001,1],bottom:[0,.001,-1],front:[0,-1,.001],back:[0,1,.001],left:[-1,0,.001],right:[1,0,.001]};
    const dir = directions[view] ? new THREE.Vector3(...directions[view]) : new THREE.Vector3(1.1, -1.6, 1.1).normalize();
    camera.position.copy(center).addScaledVector(dir, distance);
    controls.target.copy(center); camera.near = .1; camera.far = Math.max(10000, distance * 5);
    camera.updateProjectionMatrix(); controls.update();
  }
  function updateVisibility() {
    group.children.forEach(o => {
      const p=o.userData, exact=machinedBody;
      if(!exact) o.visible=(!p.circuit||visible.circuits.has(p.circuit))&&(!['drilling','plug'].includes(p.kind)||visible.drillings)&&(!['cavity','cavity-edge'].includes(p.kind)||visible.cavities)&&(!['zone','zone-edge'].includes(p.kind)||visible.zones);
      else o.visible = mode==='solid' ? ['body','edge','collision'].includes(p.kind)||xray&&p.kind==='hydraulic-net'&&visible.circuits.has(p.circuit) :
        mode==='void' ? ['machined-void','collision'].includes(p.kind) :
        mode==='features' ? (['cavity','cavity-edge'].includes(p.kind)&&visible.cavities || p.kind==='port-machining'&&visible.ports || ['zone','zone-edge','port'].includes(p.kind)&&visible.zones || ['drilling-machining','mounting-machining'].includes(p.kind)&&visible.drillings || p.kind==='plug'&&visible.closures || p.kind==='collision') :
        ['body','edge','collision'].includes(p.kind)||p.kind==='hydraulic-net'&&visible.drillings&&visible.circuits.has(p.circuit);
      if(exact&&collisionFocus)o.visible=p.kind==='collision';
      if(p.kind==='body'){const alpha=mode==='solid'?1:opacity;o.visible=o.visible&&alpha>0;o.material.opacity=alpha;o.material.transparent=alpha<1;o.material.depthWrite=alpha>=.99;o.material.depthTest=true;}
      else if(o.isMesh){o.material.depthTest=!xray;o.material.depthWrite=!xray;o.material.transparent=xray||['cavity','zone'].includes(p.kind);o.material.opacity=xray?.65:['cavity','zone'].includes(p.kind)?.38:1;}
      if(p.kind==='edge'&&mode==='review'&&opacity===0)o.visible=false;
      if(p.kind==='collision'){o.material.depthTest=true;o.material.depthWrite=true;o.renderOrder=12;}
      if(dragOwners.has(p.owner))o.visible=false;
    });
    dragGroup.children.forEach(o=>{const p=o.userData;o.visible=(!p.circuit||visible.circuits.has(p.circuit))&&(!['drilling','plug'].includes(p.kind)||visible.drillings)&&(!['cavity','cavity-edge'].includes(p.kind)||visible.cavities)&&(!['zone','zone-edge'].includes(p.kind)||visible.zones);if(o.isMesh){o.material.depthTest=!xray;o.material.depthWrite=!xray;o.material.transparent=true;o.material.opacity=.72;}});
    container.dataset.xray=String(xray);container.dataset.viewMode=mode;const stock=group.children.find(o=>o.userData.kind==='body');container.dataset.stockVisible=String(!!stock?.visible);container.dataset.stockOpacity=String(stock?.material.opacity??opacity);
    handles.children.forEach(o=>{const p=o.userData;o.visible=(p.kind!=='drilling'||visible.drillings)&&(!p.circuit||visible.circuits.has(p.circuit));});
    labelGroup.children.forEach(o => {
      const p = o.userData;
      o.visible = visible.labels && (p.kind !== 'cavity' || visible.cavities) && (p.kind !== 'drilling' || visible.drillings)
        && (!p.circuit || visible.circuits.has(p.circuit));
    });
  }
  function select(id) {
    selected = id;
    [...group.children,...dragGroup.children].forEach(o => {
      if (o.material?.emissive) {const own=o.userData.owner,net=group.children.find(x=>x.userData.owner===id)?.userData.circuit;o.material.emissive.set(own===id&&id!=='block'?'#b5a32b':own===hovered?'#507c74':net&&o.userData.circuit===net?'#1d332b':'#000000');}
    });
    for(const h of handles.children){h.material.color.set(h.userData.owner === hovered ? '#ffffff' : h.userData.owner === id ? '#a7e7c0' : '#65e4b1');h.scale.setScalar(h.userData.owner === hovered?1.25:1);}
  }
  function materializePart(p,target,metrics){
    let started=performance.now();const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(p.vertices, 3));geo.setIndex(p.triangles);
    metrics.geometry_ms+=performance.now()-started;started=performance.now();geo.computeVertexNormals();metrics.normals_ms+=performance.now()-started;
    const transparent = ['body','cavity','zone'].includes(p.kind);
    const material = new THREE.MeshStandardMaterial({ color: p.color, metalness: p.kind === 'body' ? .35 : .12,
      roughness: .6, transparent, opacity: p.kind==='body'?opacity:p.kind==='cavity'?.38:p.kind==='zone'?.1:1,
      depthWrite: !transparent, side: THREE.DoubleSide });
    const object = new THREE.Mesh(geo, material); object.userData = p;
    object.renderOrder = p.kind === 'body' ? 3 : p.kind === 'cavity' ? 2 : 0;target.add(object);
    if (['body','cavity','zone'].includes(p.kind)) {
      started=performance.now();const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color:p.kind==='body'?'#8197ad':p.kind==='cavity'?'#e1edf5':p.color, transparent:true,opacity:p.kind==='body'?.45:p.kind==='cavity'?.95:.65 }));
      metrics.edges_ms+=performance.now()-started;edges.userData={...p,kind:p.kind==='body'?'edge':p.kind+'-edge'};edges.renderOrder=4;target.add(edges);
    }
  }
  function addLabel(f,features,placement){
    if(!placement)return;
    if (f.kind === 'drilling' && !f.plugged && features.some(p => p.kind === 'port' && p.face === f.face && p.u === f.u && p.v === f.v)) return;
    const element = document.createElement('div'); element.className = 'model-label'; element.textContent = featureLabel(f,{features});
    const label = new CSS2DObject(element); label.position.set(...placement.origin).addScaledVector(new THREE.Vector3(...placement.direction), -8);
    label.userData = f; labelGroup.add(label);
  }
  function load(model, features) {
    const loadStarted=performance.now(),metrics={kind:'exact-load',geometry_ms:0,normals_ms:0,edges_ms:0,labels_ms:0};
    dragOwners.clear();
    renderedFeatures=features.map(f=>({...f}));
    references.load(model.geometry_kind,features);const first = !block; block = model.block;machinedBody=model.geometry_kind!=='parameter-preview';container.dataset.geometry=machinedBody?'machined-brep':'parameter-preview';
    deferredLayers=new Set(model.deferred_layers||[]);loadedLayers=new Set(model.loaded_layers||[]);container.dataset.deferredLayers=[...deferredLayers].join(',');container.dataset.loadedLayers=[...loadedLayers].join(',');
    collisionFocus=false;collisionButton.textContent='Isolate exact contact';
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
      addLabel(f,features,pose);
    }
    metrics.labels_ms=performance.now()-labelsStarted;metrics.load_ms=performance.now()-loadStarted;
    updateVisibility(); select(selected); if (first) fit();
    requestAnimationFrame(()=>{metrics.first_frame_ms=performance.now()-loadStarted;recordTiming(Object.fromEntries(Object.entries(metrics).map(([k,v])=>[k,typeof v==='number'?Math.round(v*100)/100:v])));});
  }
  function loadLayer(layer,parts){
    const started=performance.now(),metrics={kind:'exact-layer',layer,geometry_ms:0,normals_ms:0,edges_ms:0,labels_ms:0};
    removeObjects(group,o=>o.userData.layer===layer);
    for(const raw of parts){const p={...raw,layer};if(p.circuit&&!knownCircuits.has(p.circuit)){knownCircuits.add(p.circuit);visible.circuits.add(p.circuit);}materializePart(p,group,metrics);}
    deferredLayers.delete(layer);loadedLayers.add(layer);container.dataset.deferredLayers=[...deferredLayers].join(',');container.dataset.loadedLayers=[...loadedLayers].join(',');metrics.load_ms=performance.now()-started;updateVisibility();select(selected);
    requestAnimationFrame(()=>{metrics.first_frame_ms=performance.now()-started;recordTiming(Object.fromEntries(Object.entries(metrics).map(([k,v])=>[k,typeof v==='number'?Math.round(v*100)/100:v])));});
  }
  const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
  const knownCircuits = new Set(visible.circuits);
  function aim(e) {const rect=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);ray.setFromCamera(pointer,camera);}
  function addBoundaries(f){
    const definitionId=f.cavity_id||f.port_definition_id;if(!definitionId||f.suppressed)return;const def=design.library.find(d=>d.id===definitionId),p=pose(f,design.block),[u,v]=axes[f.face],angle=(f.rotation||0)*Math.PI/180;
    for(const boundary of def?.boundaries||[])for(const height of boundary.height?[0,boundary.height]:[0]){const outline=boundary.circle?Array.from({length:64},(_,i)=>[boundary.circle[0]+boundary.circle[2]*Math.cos(i*Math.PI/32),boundary.circle[1]+boundary.circle[2]*Math.sin(i*Math.PI/32)]):boundary.points;const points=outline.map(([x,y])=>{const q=p.origin.map((a,i)=>a-p.direction[i]*(height+.2));q[u]+=x*Math.cos(angle)-y*Math.sin(angle);q[v]+=x*Math.sin(angle)+y*Math.cos(angle);return new THREE.Vector3(...q);});points.push(points[0].clone());const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:boundary.category==='mounting-footprint'?'#f2d454':'#be8aee',depthTest:false}));line.userData={owner:f.id};line.renderOrder=9;boundaryGroup.add(line);}
  }
  function addControl(f){
    if(f.suppressed||(f.kind==='drilling'&&!f.frozen_net)||f.parent_id)return;const p=pose(f,design.block),d=new THREE.Vector3(...p.direction);
    const h=new THREE.Mesh(new THREE.RingGeometry(4,6,32),new THREE.MeshBasicMaterial({color:f.id===selected?0xffffff:0x65e4b1,side:THREE.DoubleSide,depthTest:false}));
    h.position.set(...p.origin).addScaledVector(d,f.kind==='drilling'?f.depth/2:-.3);h.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),d);h.userData={owner:f.id,kind:f.kind,circuit:f.circuit};h.renderOrder=10;handles.add(h);
    const definitionId=f.cavity_id||f.port_definition_id,def=design.library?.find(x=>x.id===definitionId),target=new THREE.Mesh(f.kind==='drilling'?new THREE.CylinderGeometry(1,1,f.depth,24):new THREE.CircleGeometry(1,32),new THREE.MeshBasicMaterial({side:THREE.DoubleSide,transparent:true,opacity:0,depthWrite:false,colorWrite:false}));
    target.position.copy(h.position);target.quaternion.copy(h.quaternion);if(f.kind==='drilling')target.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d);
    target.userData={owner:f.id,kind:f.kind,inward:d,mouthRadius:def?Math.max(...def.stages.map(s=>s.diameter))/2:f.diameter/2};hitAreas.add(target);
  }
  function setDesign(value) {
    design=value;disposeGroup(handles);disposeGroup(hitAreas);disposeGroup(boundaryGroup);
    for(const f of design.features){addBoundaries(f);addControl(f);}
    select(selected);updateVisibility();
  }
  function hitTarget(){
    const targets=hitAreas.children.filter(h=>editing&&(h.userData.kind!=='cavity'||visible.cavities)&&(h.userData.kind!=='drilling'||visible.drillings&&visible.circuits.has(design.features.find(f=>f.id===h.userData.owner)?.circuit))&&(h.userData.kind==='drilling'||camera.position.clone().sub(h.position).dot(h.userData.inward)<0));
    for(const h of targets){const mmPerPixel=2*camera.position.distanceTo(h.position)*Math.tan(THREE.MathUtils.degToRad(camera.fov/2))/Math.max(1,container.clientHeight),r=Math.max(h.userData.mouthRadius+6*mmPerPixel,12*mmPerPixel);if(h.userData.kind==='drilling')h.scale.set(r,1,r);else h.scale.setScalar(r);h.updateMatrixWorld();}
    return ray.intersectObjects(targets)[0];
  }
  function hover(id){if(hovered===id)return;hovered=id;renderer.domElement.style.cursor=id?'grab':'';renderer.domElement.title=id?`Drag ${id} on its face`:'';container.dataset.hoveredFeature=id||'';select(selected);}
  function parameterModel(value,onlyIds=null,includeBlock=true) {
    const parts=[], placements={};
    const add=(geo,p,color,kind,id,owner,circuit)=>{geo.applyQuaternion(p.q);geo.translate(...p.center);parts.push({vertices:Array.from(geo.attributes.position.array),triangles:geo.index?Array.from(geo.index.array):Array.from({length:geo.attributes.position.count},(_,i)=>i),color,kind,id,owner,circuit});geo.dispose();};
    const b=value.block;if(includeBlock)add(new THREE.BoxGeometry(b.length,b.width,b.height),{q:new THREE.Quaternion(),center:[b.length/2,b.width/2,b.height/2]},'#9ba9b9','body','block');
    const cylinder=(f,diam,start,end,color,kind,id,options={})=>{const p=pose(f,b),d=new THREE.Vector3(...p.direction),a=(f.rotation||0)*Math.PI/180,[u,v]=axes[f.face];p.origin[u]+=(options.offset_u||0)*Math.cos(a)-(options.offset_v||0)*Math.sin(a);p.origin[v]+=(options.offset_u||0)*Math.sin(a)+(options.offset_v||0)*Math.cos(a);add(new THREE.CylinderGeometry((options.kind==='cone'?options.end_diameter:diam)/2,diam/2,end-start,32),{q:new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),d),center:p.origin.map((a,i)=>a+p.direction[i]*(start+end)/2)},color,kind,id,f.id,f.circuit);};
    for(const f of value.features.filter(f=>!f.suppressed&&(!onlyIds||onlyIds.has(f.id)))) {placements[f.id]=pose(f,b);const definitionId=f.cavity_id||f.port_definition_id;if(definitionId){const d=value.library.find(d=>d.id===definitionId);for(const [i,s] of (d.cutting_primitives?.length?d.cutting_primitives:d.stages).entries())cylinder(f,s.diameter,s.start,s.end,f.kind==='port'?(value.nets.find(n=>n.id===f.circuit)?.color||'#9cc8e8'):'#b4c7da',f.kind==='port'?'port':'cavity',f.id+'-'+i,s);for(const z of f.kind==='port'?[]:d.zones){const netId=f.interface_nets[z.id],net=value.nets.find(n=>n.id===netId);cylinder(f,z.diameter,z.start,z.end,net?.color||({P:'#ef5959',T:'#459cff',A:'#41ca8b',B:'#f2d454'}[netId])||'#b08bea','zone',f.id+':'+z.id,z);}}else{cylinder(f,f.diameter,0,f.depth,value.nets.find(n=>n.id===f.circuit)?.color||({P:'#ef5959',T:'#459cff',A:'#41ca8b',B:'#f2d454'}[f.circuit])||'#b08bea',f.kind,f.id);const tip=f.tip_angle===180?0:f.diameter/2/Math.tan((f.tip_angle??118)*Math.PI/360);if(tip)cylinder(f,f.diameter,f.depth,f.depth+tip,value.nets.find(n=>n.id===f.circuit)?.color||'#b08bea',f.kind,f.id+':tip',{kind:'cone',end_diameter:0});if(f.plugged)cylinder(f,f.diameter,0,f.plug_length,'#d5dee9','plug',f.id+':plug');}}
    return {block:b,parts,placements,geometry_kind:'parameter-preview'};
  }
  function preview(value) {load(parameterModel(value),value.features);}
  function updateFeature(value,id){
    const started=performance.now(),source=value.features.find(item=>item.id===id);if(!source)return;
    const affected=new Set([id]);let changed=true;while(changed){changed=false;for(const f of value.features)if(f.parent_id&&affected.has(f.parent_id)&&!affected.has(f.id)){affected.add(f.id);changed=true;}}
    const features=value.features.map(f=>({...f,local_offset:[...(f.local_offset||[0,0])]})),byId=new Map(features.map(f=>[f.id,f]));
    const resolved=new Set();function resolveAttached(f){if(resolved.has(f.id))return;if(f.parent_id){const parent=byId.get(f.parent_id);resolveAttached(parent);const angle=(parent.rotation||0)*Math.PI/180,[u,v]=f.local_offset;f.face=parent.face;f.u=parent.u+u*Math.cos(angle)-v*Math.sin(angle);f.v=parent.v+u*Math.sin(angle)+v*Math.cos(angle);f.suppressed=f.suppressed||parent.suppressed;}resolved.add(f.id);}for(const key of affected)resolveAttached(byId.get(key));
    const current={...value,features,library:value.library};design=current;dragOwners=affected;disposeGroup(dragGroup);
    const metrics={kind:'drag-update',feature_parts:0,elapsed_ms:0,unrelated_objects:group.children.length};
    const model=parameterModel(current,affected,false),build={geometry_ms:0,normals_ms:0,edges_ms:0,labels_ms:0};
    for(const raw of model.parts){materializePart({...raw,drag_preview:true},dragGroup,build);metrics.feature_parts++;}
    for(const key of affected){const f=byId.get(key);removeObjects(labelGroup,o=>o.userData.id===key);addLabel(f,features,model.placements[key]);removeObjects(handles,o=>o.userData.owner===key);removeObjects(hitAreas,o=>o.userData.owner===key);removeObjects(boundaryGroup,o=>o.userData.owner===key);addBoundaries(f);addControl(f);}
    metrics.elapsed_ms=Math.round((performance.now()-started)*100)/100;recordTiming(metrics);updateVisibility();select(selected);
  }
  let down, drag;
  renderer.domElement.addEventListener('pointerdown', e => {
    down=[e.clientX,e.clientY];if(e.button!==0||!design||!editing)return;aim(e);
    const hit=hitTarget();if(!hit)return;
    const f=design.features.find(f=>f.id===hit.object.userData.owner);if(f.parent_id)return;
    const p=pose(f,design.block),normal=new THREE.Vector3(...p.direction),plane=new THREE.Plane().setFromNormalAndCoplanarPoint(normal,new THREE.Vector3(...p.origin));
    const point=ray.ray.intersectPlane(plane,new THREE.Vector3());if(!point)return;
    drag={f,plane,start:point,u:f.u,v:f.v,moved:false};controls.enabled=false;renderer.domElement.setPointerCapture(e.pointerId);onSelect(f.id);hover(f.id);renderer.domElement.style.cursor='grabbing';container.classList.add('dragging');e.stopImmediatePropagation();
  },true);
  renderer.domElement.addEventListener('pointermove',e=>{aim(e);if(!drag){const h=hitTarget()||ray.intersectObjects(group.children.filter(o=>o.isMesh&&o.visible&&o.userData.kind==='drilling'))[0];hover(h?.object.userData.owner||null);return;}if(!drag.moved&&Math.hypot(e.clientX-down[0],e.clientY-down[1])<3)return;const point=ray.ray.intersectPlane(drag.plane,new THREE.Vector3());if(!point)return;const [u,v]=axes[drag.f.face];const delta=point.clone().sub(drag.start).toArray();try{let [nu,nv]=clamp(drag.f,design,drag.u+delta[u],drag.v+delta[v],e.altKey?0:1);disposeGroup(guides);if(document.getElementById('smart-snap')?.checked&&!e.altKey){const aligned=smartAlign(drag.f,design,drag.u+delta[u],drag.v+delta[v],2,references.features);[nu,nv]=aligned.values;for(const g of aligned.guides){const p=pose({...drag.f,u:nu,v:nv},design.block).origin,a=[...p],b=[...p],other=g.axis===u?v:u;a[other]=0;b[other]=[design.block.length,design.block.width,design.block.height][other];guideLine(a,b,'#f2d454');}container.dataset.alignment=aligned.guides.map(g=>g.label).join(', ');}drag.moved=true;onDrag(drag.f.id,nu,nv,false);}catch{};});
  function finish(e,cancel=false){if(!drag)return false;const old=drag;drag=null;disposeGroup(guides);delete container.dataset.alignment;controls.enabled=true;container.classList.remove('dragging');renderer.domElement.style.cursor=hovered?'grab':'';if(renderer.domElement.hasPointerCapture(e.pointerId))renderer.domElement.releasePointerCapture(e.pointerId);if(old.moved)onDrag(old.f.id,cancel?old.u:design.features.find(f=>f.id===old.f.id).u,cancel?old.v:design.features.find(f=>f.id===old.f.id).v,true);return true;}
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
    const hit = ray.intersectObjects(candidates.filter(o=>o.userData.kind==='drilling'))[0]||ray.intersectObjects(candidates)[0];
    onSelect(hit ? hit.object.userData.owner || 'block' : 'block');
  });
  function resizeViewport() {
    const w = container.clientWidth, h = container.clientHeight;
    if(w<=0||h<=0)return false;
    camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h); labels.setSize(w, h);
    return true;
  }
  const resize = new ResizeObserver(() => {if(resizeViewport()&&pendingFit!==null)fit(pendingFit);});
  resize.observe(container);
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); labels.render(scene, camera); });
  return { circuitVisible(id){return visible.circuits.has(id);}, inspection(){return {geometry:machinedBody?'machined-brep':'parameter-preview',mode,xray,opacity,camera:camera.position.toArray(),target:controls.target.toArray(),deferredLayers:[...deferredLayers],loadedLayers:[...loadedLayers],diagnostics:[...diagnostics],parts:[...group.children,...dragGroup.children].filter(o=>o.isMesh).map(o=>({id:o.userData.id,kind:o.userData.kind,owner:o.userData.owner,dragPreview:!!o.userData.drag_preview,visible:o.visible,depthTest:o.material.depthTest,depthWrite:o.material.depthWrite,opacity:o.material.opacity,positions:Array.from(o.geometry.attributes.position.array)}))};}, load,loadLayer,needsLayer(layer){return deferredLayers.has(layer)&&!loadedLayers.has(layer);},updateFeature,fit,select,setDesign,preview,setReferences(value){references.reset(value);}, editing(value){editing=value;handles.visible=value;},xray(value) { xray=value;updateVisibility(); }, mode(value) { mode = value; updateVisibility(); }, opacity(value) { opacity = value; updateVisibility(); },
    toggle(key, value) { visible[key] = value; updateVisibility(); }, circuit(id, show) { show ? visible.circuits.add(id) : visible.circuits.delete(id); updateVisibility(); } };
}
