import {test} from 'node:test';
import assert from 'node:assert/strict';
import {projectSettings} from '../web/project-settings.js';
import {selectEngineeringMaterial} from '../web/engineering-inputs.js';

test('Project Settings owns engineering inputs and excludes generation and implementation parameters',()=>{
  const fields=new Map(),nodes=[],d={name:'Draft',project_context:'metric',project_defaults:{pressure_bar:null,flow_lpm:null,velocity_limit:6,drilling_mode:'orthogonal'},
    rules:{minimum_wall:null,allowable_stress_mpa:null,pressure_safety_factor:2},constraints:{preferred_wall_margin:null,priority:'fewer_plugs'},
    nets:[{id:'P',routing:'automatic',routing_variant:'simple_1'},{id:'T',routing:'manual',routing_variant:'fixed'}]};
  const element=(tag,text)=>({tag,text,children:[],append(...n){this.children.push(...n);nodes.push(...n);}}),content=element('div');
  const show=projectSettings({get:()=>d,$:()=>content,element,field:(_,label,value,onChange)=>{const field={value,onChange};fields.set(label,field);return field;},change:fn=>{fn();return true;}},{open:title=>assert.equal(title,'Project Settings')});show();
  for(const label of ['Project unit preference','Default design pressure / bar','Default flow / L/min','Default velocity limit / m/s',
    'Pressure safety factor','Minimum wall / ligament (optional) / mm','Preferred wall margin (optional) / mm','Design priority','Default drilling mode','Minimum X / mm','Maximum Z / mm'])assert(fields.has(label),label);
  assert(![...fields.keys()].some(label=>/face|OCCT|overlap|attempt|timeout|stress/i.test(label)));
  fields.get('Default design pressure / bar').onChange(250);assert.equal(d.project_defaults.pressure_bar,250);
  assert.equal(d.nets[0].routing_variant,null);assert.equal(d.nets[1].routing_variant,'fixed');
  const geometry={length:120,width:100,height:100};d.block=geometry;fields.get('Project unit preference').onChange('inch');assert.deepEqual(d.block,geometry);
});

test('material changes preserve all project criteria, defaults, legacy stress and authored geometry',()=>{
  const d={block:{length:120,width:100,height:100,material_id:'6061',stock_id:'old'},project_defaults:{pressure_bar:280},
    rules:{pressure_safety_factor:2.5,minimum_wall:5,allowable_stress_mpa:80},constraints:{preferred_wall_margin:3}};
  const before=structuredClone({rules:d.rules,constraints:d.constraints,project_defaults:d.project_defaults});
  selectEngineeringMaterial(d,{id:'316L',display_name:'316L'});
  assert.deepEqual({rules:d.rules,constraints:d.constraints,project_defaults:d.project_defaults},before);
  assert.equal(d.block.stock_id,null);assert.equal(d.block.length,120);
});
