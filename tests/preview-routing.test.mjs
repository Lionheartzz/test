import test from 'node:test';
import assert from 'node:assert/strict';
import {createPreviewRoutingState,featureNetDependencies,previewEditForProperty} from '../web/preview-routing.js';
import {EXACT_PREVIEW_IDLE_MS,EXACT_PREVIEW_CLIENT_TIMEOUT_MS,createPreviewQueue} from '../web/preview-queue.js';
const source={name:'Fixture',block:{length:160},features:[{id:'P1',circuit:'P'},{id:'CV1',interface_nets:{port1:'P',port2:'A'}},{id:'CV2',interface_nets:{port1:'T',port2:'B'}}],nets:['P','A','T','B'].map(id=>({id,routing:'automatic'}))};
const seed={source_revision:'a'.repeat(64),design:{...structuredClone(source),features:[...structuredClone(source.features),{id:'RP',route_net:'P'},{id:'RA',route_net:'A'},{id:'RT',route_net:'T'},{id:'RB',route_net:'B'}]}};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

test('explicit port/cavity actions carry correct dependencies without modifying authored JSON',()=>{
  assert.deepEqual(featureNetDependencies(source,['P1']),['P']);
  assert.deepEqual(featureNetDependencies(source,['CV1']),['A','P']);
  assert.deepEqual(previewEditForProperty('Position U / mm','CV1'),{kind:'local',feature_ids:['CV1']});
  const state=createPreviewRoutingState(),before=structuredClone(source),after=structuredClone(before);after.features[1].u=54;
  state.accept(seed,before,'epoch1');state.edit(before,after,{kind:'local',feature_ids:['CV1']},'epoch1');
  assert.deepEqual(state.context('epoch1').edit.affected_nets,['A','P']);
  assert.equal(state.display(after,'epoch1').features.length,7);
  assert.equal(after.features.length,3);assert.equal('context' in after,false);
});

test('successive edits accumulate against their seed; current proposal resets pending dependencies',()=>{
  const state=createPreviewRoutingState();state.accept(seed,source,'1');
  const one=structuredClone(source);one.features[0].u=37;
  state.edit(source,one,{kind:'local',feature_ids:['P1']},'1');
  const two=structuredClone(one);two.features[1].u=54;
  state.edit(one,two,{kind:'local',feature_ids:['CV1']},'1');
  assert.deepEqual(state.context('1').edit.feature_ids,['CV1','P1']);
  state.accept({...seed,design:state.display(two,'1')},two,'1');
  assert.equal(state.context('1').edit.kind,'none');
});

test('global rules, project switch, stale display, and unexplained edits invalidate proposal reuse',()=>{
  for(const [action,scope,usable,before] of [[{kind:'global'},'1',true,source],[{kind:'local',feature_ids:['P1']},'2',true,source],[{kind:'none'},'1',false,source],[{kind:'none'},'1',true,{...source,name:'unannounced'}]]){
    const state=createPreviewRoutingState();state.accept(seed,source,'1');state.edit(before,source,action,scope,{usable});
    assert.equal(state.context(scope),null);
  }
  assert.deepEqual(previewEditForProperty('Design priority','block'),{kind:'global'});
  assert.deepEqual(previewEditForProperty('Project name','block'),{kind:'none'});
});

test('streamed proposal starts promptly; only exact work receives idle delay, with immutable context',async()=>{
  assert.equal(EXACT_PREVIEW_IDLE_MS,1500);assert.equal(EXACT_PREVIEW_CLIENT_TIMEOUT_MS,185000);
  const calls=[],fast=[],status=[];
  const queue=createPreviewQueue({delay:5,exactDelay:100,stream:(d,o)=>new Promise(resolve=>calls.push({d,o,resolve})),
    post:()=>{throw Error('No second route resolution');},onFast:p=>fast.push(p),onExact:()=>{},onStatus:s=>status.push(s),onError:e=>{throw e;},cancelRemote:()=>{}});
  const context={edit:{kind:'local',feature_ids:['P1']}};
  queue.schedule(source,'1',context);context.edit.feature_ids.push('CV1');await sleep(20);
  assert.equal(calls.length,1);assert.ok(calls[0].o.preview.exact_idle_ms>50);
  assert.deepEqual(calls[0].o.preview.context.edit.feature_ids,['P1']);
  calls[0].o.onProposal('local route');assert.deepEqual(fast,['local route']);assert.equal(status.at(-1),'settling');
  await sleep(105);assert.equal(status.at(-1),'exact');calls[0].resolve('exact');await sleep(1);queue.cancel();
});
