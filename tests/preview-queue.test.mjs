import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPreviewQueue} from '../web/preview-queue.js';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function harness(){
 const calls=[],exact=[],contexts=[],fast=[],errors=[],status=[];
 const queue=createPreviewQueue({delay:15,exactDelay:15,post:(url,design)=>new Promise((resolve,reject)=>calls.push({url,design,resolve,reject})),onFast:r=>fast.push(r),onExact:(r,d,c)=>{exact.push(r);contexts.push(c);},onError:e=>errors.push(e.message),onStatus:s=>status.push(s)});
 return {queue,calls,exact,contexts,fast,errors,status};
}
test('rapid edits coalesce into immutable newest snapshot and one pipeline',async()=>{
 const h=harness(),d={value:1};h.queue.schedule(d);d.value=2;h.queue.schedule(d);d.value=3;h.queue.schedule(d);d.value=99;
 await sleep(30);assert.equal(h.calls.length,1);assert.deepEqual(h.calls[0].design,{value:3});
 h.queue.schedule({value:4});h.queue.schedule({value:5});await sleep(25);assert.equal(h.calls.length,1);
 h.calls[0].reject(Error('obsolete 422'));await sleep(25);assert.deepEqual(h.errors,[]);assert.equal(h.calls.length,2);
 h.calls[1].resolve('latest proposal');await sleep(25);assert.equal(h.calls.length,3);assert.equal(h.calls[2].url,'/api/preview-solid');assert.deepEqual(h.calls[2].design,{value:5});
 h.calls[2].resolve('exact');await sleep(5);assert.deepEqual(h.exact,['exact']);
 h.queue.schedule({value:5});await sleep(25);assert.equal(h.calls.length,4);assert.equal(h.calls[3].url,'/api/preview-solid');h.calls[3].resolve('refreshed exact');await sleep(5);h.queue.cancel();
});

test('cached exact core refreshes a current context before lazy layers may attach',async()=>{
 const h=harness(),a={value:'A'};h.queue.schedule(a);await sleep(25);h.calls[0].resolve('A fast');await sleep(25);h.calls[1].resolve('A exact');await sleep(5);
 const first=h.contexts[0];h.queue.schedule({value:'B'});h.queue.schedule(a);
 assert.deepEqual(h.exact,['A exact','A exact']);assert.equal(h.contexts[1],null);
 await sleep(10);assert.equal(h.calls.at(-1).url,'/api/preview-solid');assert.deepEqual(h.calls.at(-1).design,a);
 h.calls.at(-1).resolve('A refreshed');await sleep(5);
 assert.ok(h.contexts.at(-1).version>first.version);assert.equal(h.contexts.at(-1).owner,first.owner);h.queue.cancel();
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

test('remote cancellation releases hung obsolete request and newest snapshot wins',async()=>{
 const calls=[],cancels=[],shown=[],errors=[];
 const queue=createPreviewQueue({delay:5,exactDelay:5,timeout:1000,
  post:(url,design,options)=>new Promise(resolve=>calls.push({url,design,options,resolve})),
  cancelRemote:(owner,version)=>cancels.push({owner,version}),onFast:()=>{},onExact:r=>shown.push(r),onStatus:()=>{},onError:e=>errors.push(e.message)});
 queue.schedule({value:1});await sleep(15);calls[0].resolve('first fast');await sleep(15);
 const obsolete=calls[1];queue.schedule({value:2});queue.schedule({value:3});await sleep(15);
 assert.equal(obsolete.options.signal.aborted,true);assert.equal(calls.length,3);
 assert.deepEqual(calls[2].design,{value:3});assert.ok(cancels.some(c=>c.version===1));
 calls[2].resolve('new fast');await sleep(15);calls[3].resolve('new exact');await sleep(5);
 obsolete.resolve('stale exact');await sleep(5);assert.deepEqual(shown,['new exact']);assert.deepEqual(errors,[]);queue.cancel();
});

test('hung exact request times out visibly, retains usable view, then recovers',async()=>{
 const calls=[],shown=[],errors=[],states=[],cancels=[];
 const queue=createPreviewQueue({delay:5,exactDelay:5,timeout:40,
  post:(url,design,options)=>new Promise(resolve=>calls.push({url,design,options,resolve})),
  cancelRemote:(owner,version)=>cancels.push(version),onFast:()=>{},onExact:r=>shown.push(r),onStatus:s=>states.push(s),onError:e=>errors.push(e.message)});
 queue.schedule({value:1});await sleep(10);calls[0].resolve('fast');await sleep(10);calls[1].resolve('usable exact');await sleep(5);
 queue.schedule({value:2});await sleep(10);calls[2].resolve('fast');await sleep(60);
 assert.equal(states.at(-1),'error');assert.match(errors[0],/interactive time limit.*Last usable view retained/);
 assert.deepEqual(shown,['usable exact']);assert.equal(calls[3].options.signal.aborted,true);assert.ok(cancels.includes(2));
 queue.schedule({value:3});await sleep(10);calls[4].resolve('fast');await sleep(10);calls[5].resolve('recovered');await sleep(5);
 assert.equal(states.at(-1),'ready');assert.deepEqual(shown,['usable exact','recovered']);queue.cancel();
});
