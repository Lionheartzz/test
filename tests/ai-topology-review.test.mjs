import test from 'node:test';
import assert from 'node:assert/strict';
import {readTopologyReview,topologyReviewChanges} from '../web/ai-generation.js';

test('review import is bounded and scoped to the current analysis',async()=>{
  const task={id:'task'},run={id:'run',input_revision:'rev'};
  const packet={schema_version:1,task_id:'task',run_id:'run',input_revision:'rev'};
  assert.deepEqual(await readTopologyReview({size:100,text:async()=>JSON.stringify(packet)},task,run),packet);
  await assert.rejects(readTopologyReview({size:200001},task,run),/too large/);
  await assert.rejects(readTopologyReview({size:100,text:async()=>JSON.stringify({...packet,run_id:'old'})},task,run),/different analysis/);
});

test('preview identifies label, disposition and real net differences without mutation',()=>{
  const before={ports:[{id:'p',component_id:'C',label:'3',disposition:'connected'},{id:'unused',component_id:'C',label:'1'}],nets:[{id:'N',label:'Wrong net',members:['p','unused']}]};
  const snapshot=structuredClone(before),after={ports:[{id:'p',component_id:'C',label:'1',disposition:'connected'},{id:'unused',component_id:'C',label:'1',disposition:'terminated'}],nets:[{id:'NEW',label:'Correct net',members:['p']}]};
  const rows=topologyReviewChanges(before,after);
  assert.equal(rows.length,2);assert.deepEqual(rows[0].after,['1','connected','Correct net']);
  assert.deepEqual(rows[1].after,['1','terminated','No net']);assert.deepEqual(before,snapshot);
});
