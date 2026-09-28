import test from 'node:test';
import assert from 'node:assert/strict';
import {createRouteRefineFlight} from '../web/route-refine.js';

function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function harness(){
  const pending=[],editing=[],notices=[],previews=[];
  let epoch=1,draft={id:'route',features:[{id:'B1',frozen_net:'P'}]};
  const flight=createRouteRefineFlight({
    snapshot:id=>({epoch,signature:JSON.stringify(draft),id,owner:draft.features.find(f=>f.id===id)?.frozen_net}),
    isCurrent:g=>g.epoch===epoch&&g.signature===JSON.stringify(draft)&&draft.features.some(f=>f.id===g.id&&f.frozen_net===g.owner),
    cancelPreview:async()=>{},submit:input=>{const item=deferred();pending.push({input,...item});return item.promise;},
    setEditing:value=>editing.push(value),
    apply:result=>{draft=result.design;notices.push('checked');},
    settle:()=>previews.push(JSON.stringify(draft)),
    reportError:error=>notices.push(error.message)
  });
  return {flight,pending,editing,notices,previews,setDraft:value=>draft=value,setEpoch:value=>epoch=value};
}

test('two rapid route completions are single-flight and preview resumes only after success',async()=>{
  const h=harness(),first=h.flight.run({id:'B1',u:1}),second=h.flight.run({id:'B1',u:2});
  await Promise.resolve();await Promise.resolve();
  assert.equal(h.pending.length,1);assert.equal(h.flight.pending,true);assert.deepEqual(h.previews,[]);
  assert.equal(await second,false);
  h.pending[0].resolve({design:{id:'checked',features:[{id:'B1',frozen_net:'P'}]}});
  assert.equal(await first,true);assert.deepEqual(h.editing,[false,true]);
  assert.equal(h.flight.pending,false);assert.equal(h.previews.length,1);
});

test('a real refine error restores editing and preserves the current draft for retry',async()=>{
  const h=harness(),run=h.flight.run({id:'B1'});
  await Promise.resolve();await Promise.resolve();h.pending[0].reject(Error('real 422'));
  assert.equal(await run,false);assert.deepEqual(h.notices,['real 422']);
  assert.deepEqual(h.editing,[false,true]);assert.equal(h.previews.length,1);
  const retry=h.flight.run({id:'B1'});await Promise.resolve();await Promise.resolve();
  assert.equal(h.pending.length,2);h.pending[1].reject(Error('expected 409'));
  assert.equal(await retry,false);assert.equal(h.flight.pending,false);
  assert.deepEqual(h.editing,[false,true,false,true]);
});

test('stale project or edited draft cannot receive old refine result',async()=>{
  const h=harness(),old=h.flight.run({id:'B1'});
  await Promise.resolve();await Promise.resolve();h.setEpoch(2);
  h.setDraft({id:'new-project',features:[{id:'B1',frozen_net:'P'}]});
  h.pending[0].resolve({design:{id:'stale',features:[{id:'B1',frozen_net:'P'}]}});
  assert.equal(await old,false);assert.deepEqual(h.notices,[]);
  assert.deepEqual(h.editing,[false,true]);assert.deepEqual(h.previews,[JSON.stringify({id:'new-project',features:[{id:'B1',frozen_net:'P'}]})]);
});

test('a newer draft signature discards the old result without losing editing',async()=>{
  const h=harness(),old=h.flight.run({id:'B1'});
  await Promise.resolve();await Promise.resolve();
  h.setDraft({id:'edited-in-place',features:[{id:'B1',frozen_net:'P'}]});
  h.pending[0].resolve({design:{id:'stale',features:[{id:'B1',frozen_net:'P'}]}});
  assert.equal(await old,false);
  assert.deepEqual(h.notices,[]);
  assert.deepEqual(h.editing,[false,true]);
  assert.match(h.previews[0],/edited-in-place/);
});

test('refine waits for transient preview cancellation acknowledgement',async()=>{
  const cancel=deferred(),request=deferred(),events=[];
  const flight=createRouteRefineFlight({
    snapshot:()=>({epoch:1}),isCurrent:()=>true,
    cancelPreview:()=>{events.push('cancel');return cancel.promise;},
    submit:()=>{events.push('refine');return request.promise;},
    setEditing:value=>events.push(value?'editing':'locked'),
    apply:()=>events.push('applied'),settle:()=>events.push('preview'),reportError:()=>events.push('error')
  });
  const run=flight.run({id:'B1'});
  assert.deepEqual(events,['locked','cancel']);
  assert.equal(flight.pending,true);
  cancel.resolve();await Promise.resolve();await Promise.resolve();
  assert.deepEqual(events,['locked','cancel','refine']);
  request.resolve({});assert.equal(await run,true);
  assert.deepEqual(events,['locked','cancel','refine','applied','editing','preview']);
});
