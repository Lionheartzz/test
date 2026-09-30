import test from 'node:test';
import assert from 'node:assert/strict';
import {createPreviewRoutingState} from '../web/preview-routing.js';
test('retained nets keep their recorded template; changing project clears it',()=>{
  const state=createPreviewRoutingState(),source={features:[],nets:[]};
  state.accept({source_revision:'a'.repeat(64),design:source,routes:[{net:'P',variant:'simple_46'},{net:'A',variant:'xyz:nearest:direct'}]},source,'1');
  state.accept({source_revision:'a'.repeat(64),design:source,routes:[{net:'P',variant:'simple_47'},{net:'A',variant:'retained'}]},source,'1');
  assert.deepEqual(state.context('1').variants,{P:'simple_47',A:'xyz:nearest:direct'});
  state.clear();state.accept({source_revision:'a'.repeat(64),design:source},source,'2');
  assert.deepEqual(state.context('2').variants,{});
});
