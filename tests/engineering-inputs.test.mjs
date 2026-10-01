import {test} from 'node:test';
import assert from 'node:assert/strict';
import {setDesignPriority,selectEngineeringMaterial,validStockSizes,selectRawStock,
  setEnvelopeMaximum,customPortDescription} from '../web/engineering-inputs.js';
import {portSetup,customPort} from '../web/port-setup.js';

const design=()=>({block:{length:120,width:120,height:100,material:'Legacy text',material_id:null},
  rules:{allowable_stress_mpa:80,pressure_safety_factor:3,minimum_wall:9},
  constraints:{priority:'fewer_plugs',preferred_wall_margin:5,envelope_max:null},
  nets:[{id:'AUTO',routing:'automatic',routing_variant:'xyz:nearest:direct'},
        {id:'MANUAL',routing:'manual',routing_variant:'xyz:nearest:direct'}],
  features:[{id:'FROZEN',frozen_net:'MANUAL'}],project_context:'metric'});

test('priority invalidates only automatic choices and keeps frozen/manual data',()=>{
  const d=design(),fixed=structuredClone(d.features);setDesignPriority(d,'short_drills');
  assert.equal(d.nets[0].routing_variant,null);assert.equal(d.nets[1].routing_variant,'xyz:nearest:direct');
  assert.deepEqual(d.features,fixed);
});

test('source material applies policy once without guessing stress or retaining stock',()=>{
  const d=design();d.block.stock_id='old';selectEngineeringMaterial(d,{id:'material_1',display_name:'Aluminum'});
  assert.equal(d.block.material_id,'material_1');assert.equal(d.block.material,'Aluminum');
  assert.equal(d.block.stock_id,null);assert.equal(d.rules.allowable_stress_mpa,null);
  assert.equal(d.rules.pressure_safety_factor,2);assert.equal(d.rules.minimum_wall,7);
  assert.equal(d.constraints.preferred_wall_margin,4);
  d.rules.minimum_wall=8;validStockSizes(d,{id:'material_1',stock:[]});assert.equal(d.rules.minimum_wall,8);
});

test('REV2 allowable default uses only resolved semantics and preserves same-material overrides',()=>{
  const d=design(),material={id:'material_rev2_6061',display_name:'6061 · T6',engineering_facts_summary:{facts:{
    yield_strength:{status:'SOURCE_BACKED',value:276},allowable_stress_mpa:{status:'NOT_AVAILABLE',value:null}}}};
  selectEngineeringMaterial(d,material);assert.equal(d.rules.allowable_stress_mpa,null);
  Object.assign(d.rules,{allowable_stress_mpa:123,pressure_safety_factor:3,minimum_wall:9});d.constraints.preferred_wall_margin=6;
  d.block.stock_id='approved';selectEngineeringMaterial(d,material);
  assert.equal(d.rules.allowable_stress_mpa,123);assert.equal(d.rules.pressure_safety_factor,3);
  assert.equal(d.rules.minimum_wall,9);assert.equal(d.constraints.preferred_wall_margin,6);assert.equal(d.block.stock_id,'approved');
  selectEngineeringMaterial(d,{id:'material_other',display_name:'Other',engineering_facts_summary:{facts:{allowable_stress_mpa:{status:'SOURCE_BACKED',value:150}}}});
  assert.equal(d.rules.allowable_stress_mpa,150);assert.equal(d.block.stock_id,null);
  assert.equal(d.rules.pressure_safety_factor,2);assert.equal(d.rules.minimum_wall,7);assert.equal(d.constraints.preferred_wall_margin,4);
});

test('raw stock is source filtered, optional, and independent of finished dimensions',()=>{
  const d=design();selectEngineeringMaterial(d,{id:'material_1',display_name:'Aluminum'});
  const stock={id:'stock_test',material_id:'material_1',active:1,unit_system:'metric',size_1_mm:130,size_2_mm:110,allowance_1_mm:2,allowance_2_mm:3};
  const material={id:'material_1',stock:[stock,{...stock,id:'wrong',material_id:'material_2'},
    {...stock,id:'inactive',active:0},{...stock,id:'too_small',size_1_mm:100}]};
  assert.deepEqual(validStockSizes(d,material),[stock]);assert.equal(d.block.stock_id,null);
  selectRawStock(d,stock);assert.deepEqual([d.block.length,d.block.width,d.block.height],[120,120,100]);
  assert.deepEqual(d.block.stock_dimensions,[120,130,110]);assert.deepEqual(d.block.machining_allowance,[0,2,3]);
  assert.deepEqual(d.block.stock_excess,[0,5,5]);selectRawStock(d,null);assert.equal(d.block.stock_id,null);
});

test('optional numeric envelope axes preserve the supported tuple constraint',()=>{
  const d=design();setEnvelopeMaximum(d,0,160);assert.deepEqual(d.constraints.envelope_max,[160,2000,2000]);
  setEnvelopeMaximum(d,1,200);assert.deepEqual(d.constraints.envelope_max,[160,200,2000]);
  setEnvelopeMaximum(d,0,null);setEnvelopeMaximum(d,1,null);assert.equal(d.constraints.envelope_max,null);
  assert.throws(()=>setEnvelopeMaximum(d,2,0));
});

test('one-off port setup exposes engineering dimensions without specification text',()=>{
  const labels=[],element=(tag,text)=>({tag,text,children:[],append(...nodes){this.children.push(...nodes);}});
  const parent=element('div'),ctx={element,field:(_,label)=>labels.push(label),action(){},api(){}};
  portSetup(ctx,parent,customPort(),'P',()=>{});
  assert.ok(labels.includes('P · Diameter / mm'));assert.ok(labels.includes('P · Cylinder depth / mm'));
  assert.ok(!labels.some(label=>/specification|note/i.test(label)));
  assert.equal(customPortDescription(12,20),'Custom Ø12 × 20 mm');
});
