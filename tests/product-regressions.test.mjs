import {test} from 'node:test';
import assert from 'node:assert/strict';
import {featureLabel,returnNetToAutomatic} from '../web/kinematics.js';

test('generated route labels hide hash ids and keep a deterministic cavity/net alias',()=>{
  const design={features:[
    {id:'CV1',kind:'cavity'},
    {id:'R-5c62e091-1',kind:'drilling',route_net:'P',connects_to:['CV1:port1']},
    {id:'R-5c62e091-2',kind:'drilling',route_net:'P',connects_to:['R-5c62e091-1']},
  ]};
  assert.equal(featureLabel(design.features[1],design),'CV1-P1');
  assert.equal(featureLabel(design.features[2],design),'CV1-P2');
});

test('returning a refined route to automatic removes only owned geometry and stale contacts',()=>{
  const design={nets:[{id:'P',routing:'manual',routing_variant:'xyz:nearest:direct',construction_access:[{face:'top',u:1,v:2}]},{id:'T',routing:'automatic'}],features:[
    {id:'CV1',kind:'cavity',connects_to:[]},
    {id:'P-FROZEN',kind:'drilling',frozen_net:'P',connects_to:['CV1:port1']},
    {id:'T-ROUTE',kind:'drilling',route_net:'T',connects_to:['P-FROZEN']},
  ]};
  returnNetToAutomatic(design,'P');
  assert.deepEqual(design.features.map(f=>f.id),['CV1','T-ROUTE']);
  assert.deepEqual(design.features[1].connects_to,[]);
  assert.equal(design.nets[0].routing,'automatic');assert.equal(design.nets[0].routing_variant,null);assert.deepEqual(design.nets[0].construction_access,[]);
  assert.equal(design.nets[1].routing,'automatic');
});
