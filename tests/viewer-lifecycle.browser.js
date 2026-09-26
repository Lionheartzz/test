// Browser integration fixture, bundled by scripts/check-viewer-lifecycle.mjs.
// Exercises the actual viewer's pointer -> callback -> preview -> load lifecycle.
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
  // Use the Viewer's actual active camera; the test must not copy Fit maths.
  const point=(u,v)=>viewer.project([0,u,v]);
  window.viewerLifecycle={frames,point,edited,viewer,container,draft};
  return {start:point(40,66),moves:[point(43.2,65.5),point(43.1,65.6),point(43.3,65.4),point(43.2,65.5)]};
};

window.prepareOrthographicLifecycle=()=>{
  const {viewer,point}=window.viewerLifecycle;
  if(!viewer.projection('orthographic'))throw Error('Orthographic projection switch failed');
  viewer.fit('left');
  return {start:point(42,67),moves:[point(43.2,65.5),point(43.1,65.6),point(43.3,65.4),point(43.2,65.5)]};
};

window.assertViewerLifecycle=async()=>{
  const {frames,viewer,container}=window.viewerLifecycle;
  const moves=frames.filter(f=>!f.done);
  if(moves.length<4)throw Error('Continuous drag did not deliver four pointer movements: '+JSON.stringify(frames));
  for(const frame of moves){
    if(frame.u!==42||frame.v!==67||!frame.alignment.includes('AUTO_OTHER'))throw Error('Generated reference lost during continuous preview/load: '+JSON.stringify(frame));
  }
  const state=viewer.inspection(),dragTimings=state.diagnostics.filter(r=>r.kind==='drag-update');
  if(state.projection!=='orthographic')throw Error('Orthographic drag did not use the active camera');
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
  viewer.preview(labels);viewer.select('CV1');await new Promise(requestAnimationFrame);if(!hasRouteLabel())throw Error('Approximate labels lost Hydraulic Net display context: '+text());
  const gizmo=viewer.inspection().localGizmo;
  if(gizmo.id!=='CV1'||!gizmo.visible||gizmo.origin.join(',')!=='30,30,60'||container.querySelectorAll('.local-gizmo-label').length!==3)throw Error('Selected feature local axes did not follow displayed placement: '+JSON.stringify({gizmo,labels:container.querySelectorAll('.local-gizmo-label').length}));
  viewer.load({block:labels.block,parts:[],placements:{CV1:{origin:[30,30,0],direction:[0,0,-1]},ROUTE_INTERNAL:{origin:[0,30,30],direction:[1,0,0]}},geometry_kind:'exact-brep'},labels);
  await new Promise(requestAnimationFrame);if(!hasRouteLabel())throw Error('Exact labels lost Hydraulic Net display context: '+text());
  if(!viewer.focus('ROUTE_INTERNAL').ok)throw Error('Focus required an owner mesh or lazy layer');
  if(!viewer.frame(['CV1','ROUTE_INTERNAL']).ok||!viewer.frame('NET_P').ok)throw Error('Multi-object or network framing did not use displayed parameter bounds');
  if(!viewer.frame({min:[0,0,0],max:[100,80,60]}).ok)throw Error('Explicit bounds framing failed');
  route.u=31;viewer.updateFeature(labels,route.id);await new Promise(requestAnimationFrame);if(!hasRouteLabel())throw Error('Incremental labels lost Hydraulic Net display context: '+text());
  labels.schematic_intent={assets:[],components:[{id:'COMP1',label:'Valve 1',placement_id:'CV1'}]};viewer.preview(labels);await new Promise(requestAnimationFrame);
  if(!text().includes('Valve 1'))throw Error('Schematic component label was unavailable to Viewer: '+text());
  if(!viewer.isolate(route.id).ok)throw Error('Parameter-preview route isolation failed');
  viewer.setClipping({enabled:true,axis:'y',position:40,keep:'gte'});
  viewer.setSecondary(['CV1']);viewer.setIssueMarkers([{id:'ROUTE_INTERNAL',FAIL:1,WARNING:0}]);viewer.hover(route.id);
  if(viewer.focus(route.id).ok)throw Error('Focus moved to a fully clipped target');
  viewer.resetTransient();
  const reset=viewer.inspection();
  if(reset.isolation||reset.clipping.enabled||reset.projection!=='orthographic'||reset.localGizmo.id||container.querySelector('.issue-marker')||container.dataset.hoveredFeature)throw Error('Transient reset leaked state or lost projection');
  return {passed:true,moves,dragTimings,hydratedSqliteDrag:true,fullDisplayContext:true,localFrame:true,localGizmo:true,transientReset:true,adoptedAutomatic:false};
};
