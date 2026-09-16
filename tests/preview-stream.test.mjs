import {test} from 'node:test';
import assert from 'node:assert/strict';
import {streamExactPreview} from '../web/preview-stream.js';
import {createPreviewQueue} from '../web/preview-queue.js';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

test('proposal arrives before exact, fragmented UTF-8 and JSON are reassembled',async t=>{
  let writer;const seen=[],timings=[];
  t.mock.method(globalThis,'fetch',async()=>new Response(new ReadableStream({start(c){writer=c;}})));
  const result=streamExactPreview({}, {onProposal:p=>seen.push(p),onTiming:t=>timings.push(t),headers:{}});
  await sleep(0);
  const bytes=new TextEncoder().encode(JSON.stringify({type:'proposal',result:{name:'阀腔'}})+'\n');
  for(const b of bytes)writer.enqueue(new Uint8Array([b]));
  await sleep(0);assert.deepEqual(seen,[{name:'阀腔'}]);
  writer.enqueue(new TextEncoder().encode('{"type":"exact","result":{"model":"BRep"}}\n'));writer.close();
  assert.deepEqual(await result,{model:'BRep'});assert.equal(timings.length,1);assert.ok(timings[0].exact_ms>=timings[0].proposal_ms&&timings[0].parse_ms>=0);
});

test('stream error or missing final result retains actual failure reason',async t=>{
  for(const body of ['{"type":"error","detail":"Exact preview exceeded 15 seconds"}\n','{"type":"proposal","result":{}}\n']){
    t.mock.method(globalThis,'fetch',async()=>new Response(body));
    await assert.rejects(streamExactPreview({}, {onProposal:()=>{},headers:{}}),/exceeded 15 seconds|ended before a usable result/);
    t.mock.restoreAll();
  }
});

test('one streamed request per immutable draft; superseded progress and results ignored',async()=>{
  const calls=[],fast=[],exact=[];
  const q=createPreviewQueue({delay:5,stream:(design,options)=>new Promise(resolve=>calls.push({design,options,resolve})),
    post:()=>{throw Error('Should not start a separate fast worker');},cancelRemote:()=>{},
    onFast:p=>fast.push(p),onExact:p=>exact.push(p),onStatus:()=>{},onError:e=>{throw e;}});
  const d={u:1};q.schedule(d);await sleep(15);d.u=2;q.schedule(d);await sleep(15);
  assert.deepEqual(calls[0].design,{u:1});assert.equal(calls[0].options.signal.aborted,true);
  calls[0].options.onProposal('obsolete');calls[0].resolve('obsolete exact');
  calls[1].options.onProposal('current');calls[1].resolve('current exact');await sleep(5);
  assert.deepEqual(fast,['current']);assert.deepEqual(exact,['current exact']);assert.equal(calls.length,2);q.cancel();
});
