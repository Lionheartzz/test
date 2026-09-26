import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {VIEW_DIRECTIONS,CORNER_VIEWS,viewDirection,cameraSpan,resizeCamera,frameCamera} from '../web/viewer-navigation.js';
import {reportSource,resolveCheckTargets,issueReferences} from '../web/validation-view.js';

test('named navigation retains the original front, back and asymmetric ISO convention',()=>{
  assert.deepEqual(VIEW_DIRECTIONS.front,[0,-1,.001]);
  assert.deepEqual(VIEW_DIRECTIONS.back,[0,1,.001]);
  assert.deepEqual(VIEW_DIRECTIONS.iso,[1.1,-1.6,1.1]);
  assert.equal(Object.keys(CORNER_VIEWS).length,8);
  assert.ok(viewDirection('front').dot(viewDirection('back'))<-.999);
  assert.ok(viewDirection('iso').dot(viewDirection('corner-rft'))>.99999);
});

test('projection span and framing preserve direction and union bounds',()=>{
  const perspective=new THREE.PerspectiveCamera(38,1,.1,10000),ortho=new THREE.OrthographicCamera(-50,50,50,-50,.1,10000);
  const target=new THREE.Vector3(5,6,7),direction=viewDirection('front');
  perspective.position.copy(target).addScaledVector(direction,180);
  const span=cameraSpan(perspective,180);
  resizeCamera(ortho,1200,600,span);
  ortho.position.copy(perspective.position);
  assert.ok(Math.abs(cameraSpan(ortho,180)-span)<1e-8);
  const controls={target:target.clone(),update(){}};
  const bounds=new THREE.Box3(new THREE.Vector3(-10,-15,-20),new THREE.Vector3(60,30,40));
  const framedSpan=frameCamera(ortho,controls,bounds,1200,600);
  assert.ok(framedSpan>0);
  assert.deepEqual(controls.target.toArray(),[25,7.5,10]);
  assert.ok(ortho.position.clone().sub(controls.target).normalize().dot(direction)>.99999);
  resizeCamera(ortho,600,1200,framedSpan);
  assert.ok(Math.abs(cameraSpan(ortho,180)-framedSpan)<1e-8);
  assert.equal(ortho.left,-framedSpan/4);
});

const displayed={features:[
  {id:'CV1',kind:'cavity',interface_nets:{P:'P'}},
  {id:'PT1',kind:'port',circuit:'P'},
  {id:'R1',kind:'drilling',route_net:'P'},
  {id:'CV2',kind:'cavity',suppressed:true,interface_nets:{T:'T'}},
],nets:[{id:'P'},{id:'T'}]};
test('validation targets use stable IDs and explicit net membership only',()=>{
  assert.deepEqual(resolveCheckTargets({items:['CV1:P','PT1','CV2']},{displayed}).ids,['CV1','PT1']);
  assert.deepEqual(resolveCheckTargets({items:['P']},{displayed}).ids,['CV1','PT1','R1']);
  const editedDisplay={...displayed,features:displayed.features.filter(feature=>feature.id!=='R1')};
  assert.deepEqual(resolveCheckTargets({items:['R1','P']},{displayed:editedDisplay}).ids,['CV1','PT1']);
  const newProposal={...editedDisplay,features:[...editedDisplay.features,{id:'R2',kind:'drilling',route_net:'P'}]};
  assert.deepEqual(resolveCheckTargets({items:['R2','P']},{displayed:newProposal}).ids,['R2','CV1','PT1']);
  assert.deepEqual(resolveCheckTargets({items:['red','CV one']},{displayed}).ids,[]);
  const refs=issueReferences({checks:[{status:'WARNING',items:['CV1']},{status:'FAIL',items:['CV1','PT1']},{status:'PASS',items:['CV1']}]},{displayed});
  assert.deepEqual(refs.find(row=>row.id==='CV1'),{id:'CV1',FAIL:1,WARNING:1});
});

test('spatial issue mapping is gated by exact source and draft signature',()=>{
  const report={design_revision:'rev-a',engine_revision:'engine-a'};
  const build={design_revision:'rev-a',engine_revision:'engine-a'};
  const base={report,build,dirty:false,stale:false,externalChange:false,draftCheckedSignature:null,draftSignature:'current',displayedDraftSignature:'current',displayedSource:'authoritative'};
  assert.equal(reportSource(base).kind,'authoritative');
  assert.equal(reportSource({...base,displayedSource:'proposal'}).spatial,false);
  assert.equal(reportSource({...base,dirty:true}).spatial,false);
  assert.equal(reportSource({...base,externalChange:true}).spatial,false);
  assert.equal(reportSource({...base,report:{...report,engine_revision:'other'}}).spatial,false);
  assert.equal(reportSource({...base,dirty:true,draftCheckedSignature:'current',displayedSource:'draft'}).kind,'draft');
  assert.equal(reportSource({...base,dirty:true,draftCheckedSignature:'current',displayedDraftSignature:'old',displayedSource:'draft'}).spatial,false);
  assert.equal(reportSource({...base,dirty:true,draftCheckedSignature:'current',displayedSource:'retained'}).spatial,false);
  assert.equal(reportSource({...base,dirty:true,draftCheckedSignature:'old'}).spatial,false);
  assert.match(reportSource({...base,dirty:true,draftCheckedSignature:'old',reportWasDraft:true}).label,/Previous draft/);
});
