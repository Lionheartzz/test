// Browser integration fixture, bundled by scripts/check-viewer-lifecycle.mjs.
// Exercises the actual viewer's pointer -> callback -> preview -> load lifecycle.
import * as THREE from 'three';
import {createViewer} from '../web/viewer.js';
import {hydrateDesign} from '../web/domain.js';

window.setupViewerLifecycle=()=>{
  document.body.innerHTML='<label><input id="smart-snap" type="checkbox" checked> Smart Align</label><div id="test-viewer" style="position:relative;width:1000px;height:800px;background:#162229"></div>';
  const container=document.querySelector('#test-viewer');
  const drill=(id,u,v)=>({id,rotation:0,kind:'drilling',face:'left',u,v,depth:80,diameter:8,tip_angle:180,circuit:'P',plugged:true,plug_length:8,clearance_diameter:16,clearance_height:10});
  const edited={...drill('REFINED',40,66),frozen_net:'P'};
  const automatic={...drill('AUTO_OTHER',42,67),route_net:'T',circuit:'T'};
  const draft={block:{length:160,width:120,height:120},library:[],features:[edited],nets:[{id:'P',color:'#ff7777'},{id:'T',color:'#66aaff'}]};
  const frames=[];
  const viewer=createViewer(container,()=>{},(id,u,v,done)=>{
    frames.push({id,u,v,done,alignment:container.dataset.alignment||''});
    edited.u=u;edited.v=v;
    if(!done)viewer.updateFeature(draft,id);
  });
  viewer.setReferences([edited,automatic]);
  viewer.preview({...draft,features:[edited,automatic]});viewer.setDesign(draft);viewer.fit('left');
  // Project the known face points using the documented fit geometry, without
  // replacing the real renderer, raycaster, pointer handlers or load method.
  const rect=container.getBoundingClientRect(),camera=new THREE.PerspectiveCamera(38,rect.width/rect.height,.1,10000);
  camera.up.set(0,0,1);
  const center=new THREE.Vector3(80,60,60),distance=Math.hypot(160,120,120)/2/Math.sin(THREE.MathUtils.degToRad(19))*1.12;
  camera.position.copy(center).addScaledVector(new THREE.Vector3(-1,0,.001),distance);camera.lookAt(center);camera.updateMatrixWorld();
  const point=(u,v)=>{const p=new THREE.Vector3(0,u,v).project(camera);return {x:rect.left+(p.x+1)*rect.width/2,y:rect.top+(1-p.y)*rect.height/2};};
  window.viewerLifecycle={frames,point,edited,viewer,container,draft};
  return {start:point(40,66),moves:[point(43.2,65.5),point(43.1,65.6),point(43.3,65.4),point(43.2,65.5)]};
};

window.assertViewerLifecycle=async()=>{
  const {frames,viewer,container}=window.viewerLifecycle;
  const moves=frames.filter(f=>!f.done);
  if(moves.length<4)throw Error('Continuous drag did not deliver four pointer movements: '+JSON.stringify(frames));
  for(const frame of moves){
    if(frame.u!==42||frame.v!==67||!frame.alignment.includes('AUTO_OTHER'))throw Error('Generated reference lost during continuous preview/load: '+JSON.stringify(frame));
  }
  const state=viewer.inspection(),dragTimings=state.diagnostics.filter(r=>r.kind==='drag-update');
  if(dragTimings.length<moves.length||state.diagnostics.filter(r=>r.kind==='exact-load').length!==1)throw Error('Pointermove rebuilt the full scene: '+JSON.stringify(state.diagnostics));
  if(!state.parts.some(p=>p.owner==='AUTO_OTHER')||!state.parts.some(p=>p.owner==='REFINED'&&p.dragPreview))throw Error('Incremental drag lost moved or unrelated geometry');
  if(state.parts.some(p=>p.owner==='REFINED'&&!p.dragPreview&&p.visible))throw Error('Old moved-feature geometry remained visible during drag');
  if(!frames.some(f=>f.done))throw Error('Pointerup did not settle the drag');
  const definition={id:'CAV_SQLITE',label:'SQLite cavity',family:'QA',unit_system:'metric',manufacturer:'',thread_note:'',stages:[{start:0,end:20,diameter:12}],zones:[{id:'port1',start:10,end:20,diameter:10,offset_u:0,offset_v:0,clip_to_cut:true}],clearance_diameter:18,clearance_height:20,cutting_primitives:[],boundaries:[],machining:[],usable:true,active:true,kind:'cavity'};
  const sqliteDraft=hydrateDesign({schema_version:2,block:{length:160,width:120,height:120},features:[{id:'CV1',kind:'cavity',face:'top',u:70,v:60,cavity_id:'CAV_SQLITE',interface_nets:{port1:'P'},connects_to:[],suppressed:false,rotation:0,cartridge_id:null,parent_id:null,local_offset:[0,0]}],nets:[{id:'P',color:'#ff7777'}]}, {CAV_SQLITE:definition});
  // hydrateDesign intentionally exposes definitions through a non-enumerable
  // runtime property. Incremental drag must retain it when it builds a moved-only view.
  if(Object.keys(sqliteDraft).includes('library'))throw Error('SQLite definition fixture is not using the real hydrated contract');
  viewer.preview(sqliteDraft);viewer.setDesign(sqliteDraft);sqliteDraft.features[0].u=74;viewer.updateFeature(sqliteDraft,'CV1');
  const hydratedState=viewer.inspection();if(!hydratedState.parts.some(p=>p.owner==='CV1'&&p.dragPreview))throw Error('Hydrated SQLite cavity did not update incrementally');
  const cavity={id:'CV1',kind:'cavity',face:'top',u:30,v:30,diameter:12,depth:20,interface_nets:{port1:'NET_P'},rotation:0,connects_to:[]};
  const route={id:'ROUTE_INTERNAL',kind:'drilling',face:'left',u:30,v:30,diameter:8,depth:50,tip_angle:180,plugged:true,plug_length:8,circuit:'NET_P',route_net:'NET_P',connects_to:['CV1:port1'],rotation:0};
  const labels={block:{length:100,width:80,height:60},library:[],nets:[{id:'NET_P',label:'P'}],features:[cavity,route],schematic_intent:null};
  const text=()=>[...container.querySelectorAll('.model-label')].map(node=>node.textContent);
  const hasRouteLabel=()=>text().some(value=>value.startsWith('CV1-P1'));
  viewer.preview(labels);await new Promise(requestAnimationFrame);if(!hasRouteLabel())throw Error('Approximate labels lost Hydraulic Net display context: '+text());
  viewer.load({block:labels.block,parts:[],placements:{CV1:{origin:[30,30,0],direction:[0,0,-1]},ROUTE_INTERNAL:{origin:[0,30,30],direction:[1,0,0]}},geometry_kind:'exact-brep'},labels);
  await new Promise(requestAnimationFrame);if(!hasRouteLabel())throw Error('Exact labels lost Hydraulic Net display context: '+text());
  route.u=31;viewer.updateFeature(labels,route.id);await new Promise(requestAnimationFrame);if(!hasRouteLabel())throw Error('Incremental labels lost Hydraulic Net display context: '+text());
  labels.schematic_intent={assets:[],components:[{id:'COMP1',label:'Valve 1',placement_id:'CV1'}]};viewer.preview(labels);await new Promise(requestAnimationFrame);
  if(!text().includes('Valve 1'))throw Error('Schematic component label was unavailable to Viewer: '+text());
  return {passed:true,moves,dragTimings,hydratedSqliteDrag:true,fullDisplayContext:true,adoptedAutomatic:false};
};
