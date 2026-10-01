import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createValidationProgress,estimateRemaining,validationProgressUI} from '../web/validate-progress.js';

const ID='a'.repeat(32),PROJECT='b'.repeat(32);
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const row=(percent=17,candidate=1)=>({operation_id:ID,project_id:PROJECT,state:'running',engine_revision:'engine',
  percent,candidate,candidate_limit:8,stage:'geometry',stage_text:'Building exact geometry',detail:`Route candidate ${candidate} of up to 8`,elapsed_s:10,
  trace_elapsed_s:8,events:[{stage:'geometry',candidate,elapsed_s:3,stage_text:'Building exact geometry'}]});
function setup(){
  const request=deferred(),states=[],timers=new Map(),saved=new Map();let sequence=0,now=0,scope='one',response=row(),calls=0;
  const progress=createValidationProgress({render:value=>states.push(value),fetchStatus:async()=>response,getScope:()=>scope,
    now:()=>now,idFactory:()=>ID,storage:{getItem:key=>saved.get(key),setItem:(key,value)=>saved.set(key,value)},
    schedule:(fn,ms)=>{const id=++sequence;timers.set(id,{fn,ms});return id;},cancel:id=>timers.delete(id)});
  const start=()=>progress.run({projectId:PROJECT,scope,key:'same-design',execute:()=>{calls++;return request.promise;}});
  const tick=async()=>{const [id,timer]=timers.entries().next().value||[];if(!timer)return;timers.delete(id);now+=timer.ms;await timer.fn();};
  return {progress,states,request,start,tick,saved,get calls(){return calls;},get latest(){return states.at(-1);},set response(value){response=value;},set scope(value){scope=value;}};
}
const complete=()=>({operation_id:ID,build:{counts:{FAIL:0}}});

test('Validate starts immediately, blocks duplicate execution, and completes only from its response',async()=>{
  const h=setup();assert.deepEqual(h.states,[]);const pending=h.start();
  assert(h.progress.pending());assert.equal(h.latest.stage,'Preparing design');assert.equal(h.latest.percent,0);
  assert.equal(await h.start(),null);assert.equal(h.calls,1);
  await h.tick();assert.equal(h.latest.stage,'Building exact geometry');assert.equal(h.latest.detail,'Route candidate 1 of up to 8');
  h.response=row(25,2);await h.tick();assert.equal(h.latest.detail,'Route candidate 2 of up to 8');
  h.response={...row(100,2),state:'complete',stage_text:'Validation complete'};await h.tick();
  assert.equal(h.latest.percent,99);assert.equal(h.latest.stage,'Finalizing validation');
  h.request.resolve(complete());await pending;assert.equal(h.latest.percent,100);assert.equal(h.latest.stage,'Validation complete');
  assert(!h.progress.pending());await h.tick();assert.equal(h.latest.visible,false);
});

test('percent is monotonic during retries and wrong-operation/project replies are ignored',async()=>{
  const h=setup(),pending=h.start();h.response=row(85,1);await h.tick();
  h.response=row(25,2);await h.tick();assert.equal(h.latest.percent,85);
  h.response={...row(99,8),operation_id:'c'.repeat(32)};await h.tick();assert.equal(h.latest.detail,'Route candidate 2 of up to 8');
  h.response={...row(99,8),project_id:'d'.repeat(32)};await h.tick();assert.equal(h.latest.percent,85);
  h.request.resolve(complete());await pending;
  const values=h.states.filter(s=>s.visible).map(s=>s.percent);assert.deepEqual(values,[...values].sort((a,b)=>a-b));
});

test('navigation hides old progress without cancelling the authoritative request',async()=>{
  const h=setup(),pending=h.start();await h.tick();h.scope='another-project';await h.tick();
  assert.equal(h.latest.visible,false);assert(h.progress.pending());
  h.request.resolve(complete());await pending;assert.equal(h.latest.visible,false);
});

test('transport error restores progress state and allows another Validate',async()=>{
  const h=setup(),pending=h.start();await h.tick();h.request.reject(Error('watchdog timeout'));
  await assert.rejects(pending,/watchdog timeout/);assert.equal(h.latest.visible,false);assert(!h.progress.pending());
});

test('first run estimates nothing; history needs same design/engine and matching candidate phase',()=>{
  const p=row(25,2),sample={key:'same',engine:'engine',seconds:50,trace_elapsed_s:48,events:[{stage:'geometry',candidate:2,elapsed_s:20}]};
  assert.equal(estimateRemaining([],'same',p),null);assert.equal(estimateRemaining([sample],'same',p),null);
  assert.equal(estimateRemaining([sample,sample],'same',p),30);
  assert.equal(estimateRemaining([sample,sample],'other-design',p),null);
  assert.equal(estimateRemaining([sample,sample],'same',{...p,engine_revision:'new-code'}),null);
  assert.equal(estimateRemaining([sample,sample],'same',{...p,candidate:3}),null);
  assert.equal(estimateRemaining([sample,sample],'same',{...p,elapsed_s:90}),null);
});

test('only successful owned completed Validate results enter bounded session history',async()=>{
  const h=setup(),pending=h.start();h.response={...row(100,2),state:'complete'};await h.tick();h.request.resolve(complete());await pending;
  const history=JSON.parse([...h.saved.values()][0]);assert.equal(history.length,1);assert.equal(history[0].engine,'engine');
});

test('compact progress renderer shows stages/timing and leaves existing results alone',()=>{
  const nodes=new Map();const root={hidden:true,dataset:{},querySelector:key=>{if(!nodes.has(key))nodes.set(key,{});return nodes.get(key);}};
  const render=validationProgressUI(root);render({visible:true,operationId:ID,percent:25,stage:'Building exact geometry',
    detail:'Route candidate 2 of up to 8',elapsed:31,eta:20,recent:['Trying alternate automatic route']});
  assert.equal(root.hidden,false);assert.equal(nodes.get('[data-validate-bar]').value,25);
  assert.equal(nodes.get('[data-validate-time]').textContent,'Elapsed 31 s · about 20 s remaining');
  render({visible:false});assert.equal(root.hidden,true);
});
