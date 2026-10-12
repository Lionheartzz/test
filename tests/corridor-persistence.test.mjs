import test from 'node:test';
import assert from 'node:assert/strict';
import {createPreviewRoutingState} from '../web/preview-routing.js';
import {routingEdit} from '../web/committed-routing.js';

test('3D Features replace transient legacy variant hints without encoding a plan',()=>{
  const source={name:'QA',block:{length:100,width:100,height:100},features:[{id:'P',kind:'port',circuit:'N'}],nets:[{id:'N',routing:'automatic',route_state:'unresolved'}]};
  const state=createPreviewRoutingState();
  state.accept({source_revision:'a'.repeat(64),design:source,routes:[{net:'N',variant:'xyz:nearest:direct'}]},source,'one');
  const planned={...structuredClone(source),features:[...source.features,{id:'CUT',kind:'drilling',route_net:'N',circuit:'N',face:'bottom',u:20,v:30,depth:40}]};
  state.accept({source_revision:'b'.repeat(64),design:planned,routes:[{net:'N',variant:null,planner:'corridor3d',candidate_id:'diagnostic-only'}]},source,'one');
  assert.deepEqual(state.context('one').variants,{});
  assert.deepEqual(state.current(source,'one').features,planned.features);
});

test('editing a saved source feature retains committed cuts until explicit Reroute',()=>{
  const source={block:{length:100,width:100,height:100},features:[{id:'P',kind:'port',circuit:'N',u:20},{id:'CUT',kind:'drilling',route_net:'N',depth:40}],nets:[{id:'N',routing:'automatic',route_state:'committed',routing_variant:null}]};
  const after=structuredClone(source);after.features[0].u=25;
  routingEdit(source,after,{kind:'local',feature_ids:['P']});
  assert.equal(after.nets[0].route_state,'stale');
  assert.deepEqual(after.features[1],source.features[1]);
});
