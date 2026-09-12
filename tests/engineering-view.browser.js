import {createViewer} from '../web/viewer.js';
window.setupEngineeringView=(fixture)=>{
  document.body.innerHTML='<div id="view" style="position:relative;width:1100px;height:760px;background:#162229"></div>';
  const container=document.querySelector('#view');
  const viewer=createViewer(container,()=>{});
  viewer.load(fixture.model,fixture.design.features);viewer.setDesign(fixture.design);viewer.editing(false);viewer.fit();
  window.engineeringView={viewer,fixture};
};
window.assertEngineeringView=(mode)=>{
  const {viewer,fixture}=window.engineeringView;viewer.mode(mode);
  const state=viewer.inspection(),visible=state.parts.filter(p=>p.visible);
  if(state.geometry!=='machined-brep'||state.xray||visible.some(p=>!p.depthTest||p.kind!=='body'&&!p.depthWrite))throw Error('Exact view lost real depth');
  const expected=mode==='review'?'hydraulic-net':mode==='void'?'machined-void':'body';
  if(!visible.some(p=>p.kind===expected))throw Error('Missing exact layer '+expected);
  if(mode==='review'&&visible.some(p=>!['body','hydraulic-net','collision'].includes(p.kind)))throw Error('Independent overlapping tubes shown in exact net view');
  if(fixture.model.collisions.length&&!visible.some(p=>p.kind==='collision'))throw Error('Cross-net collision hidden');
  return {mode,visible:visible.map(p=>({id:p.id,kind:p.kind})),depth:true};
};
window.assertEngineeringPreview=()=>{
  const {viewer,fixture}=window.engineeringView;viewer.preview(fixture.design);
  const state=viewer.inspection();if(state.geometry!=='parameter-preview')throw Error('Preview falsely labelled exact');
  const f=fixture.design.features.find(f=>!f.definition);const parts=state.parts.filter(p=>p.id===f.id+':tip');
  if((parts.length>0)!==(f.tip_angle!==180))throw Error('Incorrect preview drill tip');
  if(parts.length&&f.face==='left'){
    const xs=parts[0].positions.filter((_,i)=>i%3===0),expected=f.depth+f.diameter/2/Math.tan(f.tip_angle*Math.PI/360);
    if(Math.abs(Math.max(...xs)-expected)>.0001)throw Error('Preview tip does not match exact drilling parameters');
  }
  viewer.xray(true);if(!viewer.inspection().xray)throw Error('Explicit X-ray switch missing');
  viewer.xray(false);
  return {preview:true,tipAngle:f.tip_angle,tipPresent:parts.length>0};
};

window.assertEngineeringLayers=()=>{
  const {viewer}=window.engineeringView;
  viewer.mode('features');
  const before=viewer.inspection().parts;
  viewer.toggle('ports',false);viewer.toggle('closures',false);
  if(viewer.inspection().parts.some(p=>p.visible&&['port-machining','plug'].includes(p.kind)))throw Error('Machining / closure layers cannot be hidden independently');
  viewer.toggle('ports',true);viewer.toggle('closures',true);
  viewer.mode('solid');viewer.xray(true);
  if(!viewer.inspection().parts.some(p=>p.visible&&p.kind==='hydraulic-net'&&!p.depthTest))throw Error('Explicit solid X-ray does not expose hydraulic nets');
  viewer.xray(false);
  if(viewer.inspection().parts.some(p=>p.visible&&p.kind==='hydraulic-net'))throw Error('Solid retained always-on hydraulic overlay');
  return {layers:true,sourcePort:before.some(p=>p.kind==='port-machining'),closure:before.some(p=>p.kind==='plug'),explicitXray:true};
};

window.assertStableStockTransition=()=>{
 const {viewer,fixture}=window.engineeringView;
 viewer.mode('review');viewer.opacity(.37);viewer.circuit('P',false);viewer.preview(fixture.design);viewer.fit('front');
 const before=viewer.inspection();viewer.load(fixture.model,fixture.design.features);const after=viewer.inspection();
 const body=after.parts.find(p=>p.kind==='body');
 if(!body.visible||body.opacity!==.37||body.depthWrite||!body.depthTest)throw Error('Translucent stock context lost');
 if(JSON.stringify(before.camera)!==JSON.stringify(after.camera)||before.mode!==after.mode||before.xray!==after.xray)throw Error('Transition moved camera/mode');
 if(after.parts.some(p=>p.id==='net:P'&&p.visible))throw Error('Transition lost circuit visibility');
 viewer.opacity(0);if(viewer.inspection().parts.find(p=>p.kind==='body').visible)throw Error('Stock cannot be hidden');
 viewer.mode('solid');if(viewer.inspection().parts.find(p=>p.kind==='body').opacity!==1)throw Error('Solid must stay opaque');
 viewer.mode('review');viewer.opacity(.22);viewer.circuit('P',true);
 return {stockContext:true,opacityZero:true,cameraStable:true,circuitVisibilityStable:true};
};
