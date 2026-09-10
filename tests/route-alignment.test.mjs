import test from 'node:test';
import assert from 'node:assert/strict';
import {smartAlign,featureLabel} from '../web/kinematics.js';

const drill=(id,face,u,v)=>({id,kind:'drilling',face,u,v,depth:80,diameter:8,plugged:true,clearance_diameter:16});
const base=()=>({block:{length:160,width:120,height:120},library:[],features:[]});
test('engineering port labels preserve legacy stable IDs',()=>{
  const a={id:'PORT_1_1',kind:'port',circuit:'P'},b={id:'PORT_1_2',kind:'port',circuit:'P'};
  assert.equal(featureLabel(a,{features:[a]}),'P');
  assert.equal(featureLabel(a,{features:[a,b]}),'P1');assert.equal(featureLabel(b,{features:[a,b]}),'P2');
  assert.equal(a.id,'PORT_1_1');
});
test('unconverted automatic drilling centerline is a reference',()=>{
  const d=base(),f=drill('EDIT','left',40,66),generated={...drill('AUTO','left',42,67),route_net:'T'};d.features=[f];
  const r=smartAlign(f,d,43.2,65.5,2,[f,generated]);
  assert.deepEqual(r.values,[42,67]);assert.ok(r.guides.every(g=>g.label.includes('AUTO')));
  assert.equal(d.features.length,1,'alignment does not adopt generated geometry');
});
test('route snaps to external port centerline coordinates',()=>{
  const d=base(),f=drill('EDIT','left',41,72),port={...drill('P','front',82,73),kind:'port'};d.features=[f,port];
  assert.equal(smartAlign(f,d,41,72).values[1],73);
});
test('route snaps to transformed cavity hydraulic interface, not origin',()=>{
  const d=base(),f=drill('EDIT','left',23,96);d.features=[f,{id:'CV',kind:'cavity',face:'top',u:80,v:21,definition:'D',rotation:90}];
  d.library=[{id:'D',zones:[{id:'flow',start:20,end:30,offset_u:3,offset_v:7}]}];
  const r=smartAlign(f,d,25.2,94,2);assert.deepEqual(r.values,[24,95]);assert.ok(r.guides.every(g=>g.label==='CV:flow'));
});
test('alignment ignores suppressed routes and keeps face envelope',()=>{
  const d=base(),f=drill('EDIT','left',40,66);d.features=[f];
  const r=smartAlign(f,d,-1,119,2,[f,{...drill('HIDDEN','left',42,67),suppressed:true}]);
  assert.deepEqual(r.values,[8,112]);assert.ok(!r.guides.some(g=>g.label.includes('HIDDEN')));
});
