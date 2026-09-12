import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPreviewQueue} from '../web/preview-queue.js';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function harness(){
 const calls=[],exact=[],fast=[],errors=[],status=[];
 const queue=createPreviewQueue({delay:15,exactDelay:15,post:(url,design)=>new Promise((resolve,reject)=>calls.push({url,design,resolve,reject})),onFast:r=>fast.push(r),onExact:r=>exact.push(r),onError:e=>errors.push(e.message),onStatus:s=>status.push(s)});
 return {queue,calls,exact,fast,errors,status};
}
test('rapid edits coalesce into immutable newest snapshot and one pipeline',async()=>{
 const h=harness(),d={value:1};h.queue.schedule(d);d.value=2;h.queue.schedule(d);d.value=3;h.queue.schedule(d);d.value=99;
 await sleep(30);assert.equal(h.calls.length,1);assert.deepEqual(h.calls[0].design,{value:3});
 h.queue.schedule({value:4});h.queue.schedule({value:5});await sleep(25);assert.equal(h.calls.length,1);
 h.calls[0].reject(Error('obsolete 422'));await sleep(25);assert.deepEqual(h.errors,[]);assert.equal(h.calls.length,2);
 h.calls[1].resolve('latest proposal');await sleep(25);assert.equal(h.calls.length,3);assert.equal(h.calls[2].url,'/api/preview-solid');assert.deepEqual(h.calls[2].design,{value:5});
 h.calls[2].resolve('exact');await sleep(5);assert.deepEqual(h.exact,['exact']);
 h.queue.schedule({value:5});await sleep(25);assert.equal(h.calls.length,3);h.queue.cancel();
});
test('new edit during CAD never launches concurrent CAD or displays old result',async()=>{
 const h=harness();h.queue.schedule({value:1});await sleep(25);h.calls[0].resolve('fast');await sleep(25);
 h.queue.schedule({value:2});await sleep(25);assert.equal(h.calls.length,2);
 h.calls[1].resolve('old exact');await sleep(25);assert.deepEqual(h.exact,[]);assert.equal(h.calls.length,3);
 h.calls[2].reject(Error('features.0.depth: must be positive'));await sleep(5);
 assert.deepEqual(h.errors,['features.0.depth: must be positive']);assert.equal(h.status.at(-1),'error');h.queue.cancel();
});
test('settling edits skip superseded exact requests; cancellation invalidates responses',async()=>{
 const h=harness();h.queue.schedule({value:1});await sleep(25);h.calls[0].resolve('fast');await sleep(1);
 h.queue.schedule({value:2});await sleep(25);assert.equal(h.calls[1].url,'/api/preview');
 h.queue.cancel();h.calls[1].resolve('old fast');await sleep(30);assert.equal(h.calls.length,2);assert.deepEqual(h.fast,['fast']);
});
