function alias(object,name,get,set){Object.defineProperty(object,name,{configurable:true,enumerable:false,get,set});}

export function hydrateDesign(design,definitions={},threads={}){
  if(!design)return design;
  const values=Array.isArray(definitions)?definitions:Object.values(definitions||{});
  alias(design,'library',()=>values,()=>{throw Error('Engineering definitions are read-only SQLite data');});
  const threadValues=Array.isArray(threads)?threads:Object.values(threads||{});
  alias(design,'threads',()=>threadValues,()=>{throw Error('Thread definitions are read-only SQLite data');});
  alias(design,'components',()=>design.schematic_intent?.components||[],()=>{throw Error('Set schematic_intent explicitly');});
  alias(design,'schematics',()=>design.schematic_intent?.assets||[],()=>{throw Error('Set schematic_intent explicitly');});
  for(const feature of design.features||[]){
    alias(feature,'definition',()=>feature.kind==='cavity'?feature.cavity_id:feature.port_definition_id,value=>{if(feature.kind==='cavity')feature.cavity_id=value;else feature.port_definition_id=value;});
    alias(feature,'circuits',()=>feature.interface_nets||{},value=>feature.interface_nets=value);
  }
  for(const component of design.schematic_intent?.components||[]){
    alias(component,'feature_id',()=>component.placement_id,value=>component.placement_id=value||null);
    alias(component,'cavity_definition',()=>component.cavity_id,value=>component.cavity_id=value||null);
    alias(component,'ports',()=>component.interface_nets||{},value=>component.interface_nets=value);
  }
  return design;
}

export function cloneDesign(design){return hydrateDesign(structuredClone(design),Object.fromEntries((design.library||[]).map(d=>[d.id,d])),Object.fromEntries((design.threads||[]).map(d=>[d.id,d])));}
