// Browser integration fixture, bundled by scripts/check-viewer-lifecycle.mjs.
// Exercises the actual viewer's pointer -> callback -> preview -> load lifecycle.
import * as THREE from 'three';
import {createViewer} from '../web/viewer.js';

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
    // This is the synchronous production callback before any debounced response.
    viewer.preview(draft);viewer.setDesign(draft);
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

window.assertViewerLifecycle=()=>{
  const {frames}=window.viewerLifecycle;
  const moves=frames.filter(f=>!f.done);
  if(moves.length<4)throw Error('Continuous drag did not deliver four pointer movements: '+JSON.stringify(frames));
  for(const frame of moves){
    if(frame.u!==42||frame.v!==67||!frame.alignment.includes('AUTO_OTHER'))throw Error('Generated reference lost during continuous preview/load: '+JSON.stringify(frame));
  }
  return {passed:true,moves,adoptedAutomatic:false};
};
