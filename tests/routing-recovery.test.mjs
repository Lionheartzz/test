import test from 'node:test';
import assert from 'node:assert/strict';
import {createPreviewRoutingState} from '../web/preview-routing.js';
import {currentRouteDesign,preserveRoutingDraft,routingEdit} from '../web/committed-routing.js';
import {createPreviewQueue} from '../web/preview-queue.js';
const draft=()=>({schema_version:4,name:'Recovery',block:{length:160,width:160,height:160},features:[{id:'P',circuit:'P',u:40},{id:'T',circuit:'T'}, {id:'oldP',route_net:'P'},{id:'fixed',frozen_net:'T'}],nets:[{id:'P',routing:'automatic',route_state:'unresolved',members:['P','C:1']},{id:'T',routing:'manual',members:[]}]});
const proposal=d=>({source_revision:'a'.repeat(64),design:{...structuredClone(d),features:d.features.filter(f=>f.id!=='oldP').concat({id:'newP',route_net:'P'}),nets:d.nets.map(n=>n.id==='P'?{...n,route_state:'proposal',routing_variant:'simple_0'}:n)}});
test('an owned early routing result survives exact display failure; stale viewer is never read',()=>{
  const d=draft(),state=createPreviewRoutingState();state.accept(proposal(d),d,'one');
  const current=currentRouteDesign(d,state.current(d,'one'));
  assert.equal(current.nets[0].route_state,'committed');assert.ok(current.features.some(f=>f.id==='newP'));
  assert.ok(!current.features.some(f=>f.id==='oldP'));
  const moved=structuredClone(d);moved.features[0].u=42;
  assert.equal(state.current(moved,'one'),null);assert.equal(state.current(d,'two'),null);
  assert.throws(()=>currentRouteDesign(moved,state.current(moved,'one')),/Retry Routing/);
  assert.throws(()=>currentRouteDesign(d,state.current(d,'one'),{externalChange:true}),/Saved project changed/);
});
test('draft preservation excludes unresolved generated cuts and preserves manual/frozen authored work',()=>{
  const d=draft(),saved=preserveRoutingDraft(d);
  assert.equal(d.features.length,4);assert.equal(saved.features.length,3);
  assert.ok(saved.features.some(f=>f.id==='fixed'));assert.equal(saved.nets[0].route_state,'unresolved');
  assert.equal(saved.nets[0].routing_variant,null);
});
test('edit invalidates only its automatic net and retry restores current ownership',()=>{
  const d=draft(),state=createPreviewRoutingState();state.accept(proposal(d),d,'one');
  const moved=structuredClone(d);moved.features[0].u=52;
  const action=routingEdit(d,moved,{kind:'local',feature_ids:['P']});state.edit(d,moved,action,'one');
  assert.equal(state.current(moved,'one'),null);state.clear('retry');state.accept(proposal(moved),moved,'one');
  assert.equal(currentRouteDesign(moved,state.current(moved,'one')).features[0].u,52);
});
test('cancel then retry ignores superseded responses and error clears pending request',async()=>{
  const deferred=[];const accepted=[],errors=[];
  const queue=createPreviewQueue({post:()=>new Promise(resolve=>deferred.push(resolve)),onFast:r=>accepted.push(r),onExact:r=>accepted.push(r),onProposal:()=>{},onStatus:()=>{},onError:e=>errors.push(e),cancelRemote:async()=>{},delay:0,exactDelay:0});
  queue.schedule({name:'old'},'one',{},{immediate:true});await new Promise(r=>setTimeout(r,10));
  await queue.cancel();queue.schedule({name:'current'},'two',null,{immediate:true});
  await new Promise(r=>setTimeout(r,10));deferred[0]({stale:true});deferred[1]({current:true});
  await new Promise(r=>setTimeout(r,10));assert.ok(!accepted.some(r=>r.stale));assert.ok(accepted.some(r=>r.current));
  await queue.cancel();assert.equal(errors.length,0);
});
