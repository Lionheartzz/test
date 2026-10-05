import {featureNetDependencies} from './preview-routing.js';
const signature=value=>JSON.stringify(value);
const owned=design=>new Set((design.nets||[]).filter(n=>n.routing==='automatic').map(n=>n.id));
const effective=(d,n)=>[n.pressure_bar??d.project_defaults?.pressure_bar??null,n.flow_lpm??d.project_defaults?.flow_lpm??null,n.velocity_limit??d.project_defaults?.velocity_limit??6,n.diameter_mode,n.diameter];
const geometry=d=>signature([d.block.length,d.block.width,d.block.height,d.features,d.engravings,d.block_modifiers]);

export function presentationOnly(before,after){
  const key=d=>{const value=structuredClone(d);delete value.name;for(const n of value.nets||[]){delete n.label;delete n.color;}return signature(value);};
  return key(before)===key(after);
}

export function routingEdit(before,after,edit){
  if(edit.kind==='proposal')return {kind:'none',immediate:true};
  const automatic=owned(after),previous=new Map((before.nets||[]).map(n=>[n.id,n]));
  if(edit.kind==='reroute')return {kind:'global',immediate:true};
  for(const net of after.nets||[]){
    const old=previous.get(net.id);
    if(automatic.has(net.id)&&old&&signature(old.construction_access)!==signature(net.construction_access)){
      net.route_state='unresolved';net.route_issue='';net.routing_variant=null;
      return {kind:'global',immediate:true};
    }
  }
  if(geometry(before)===geometry(after)){
    const rules=signature(before.rules)!==signature(after.rules)||before.block.material_id!==after.block.material_id;
    const conditions=[],resize=[];
    for(const net of after.nets||[]){
      const old=previous.get(net.id);if(!old)continue;
      const a=effective(before,old),b=effective(after,net);
      if(rules||signature(a)!==signature(b)){conditions.push(net.id);if(signature(a.slice(1))!==signature(b.slice(1)))resize.push(net.id);}
      else if(automatic.has(net.id)&&(before.project_context!==after.project_context||signature(before.constraints)!==signature(after.constraints)||old.drilling_mode!==net.drilling_mode||before.project_defaults?.drilling_mode!==after.project_defaults?.drilling_mode||old.preferred_axis!==net.preferred_axis||old.entry_preference!==net.entry_preference)){
        if((net.route_state||'unresolved')==='unresolved')return {kind:'global',immediate:true};
        if((net.route_state||'unresolved')!=='unresolved'){net.route_state='stale';net.route_issue=`Route ${net.id} retained. Optimize or Reroute to apply the changed routing policy.`;}
      }
    }
    for(const net of after.nets||[])if(automatic.has(net.id)&&conditions.includes(net.id)&&(net.route_state||'unresolved')!=='unresolved'){
      net.route_state='stale';net.route_issue=`Route ${net.id} needs review after the hydraulic-condition change. Reroute if it no longer meets requirements.`;
    }
    return conditions.length?{kind:'conditions',affected_nets:conditions.sort(),resize_nets:resize.sort(),immediate:true}:{kind:'none'};
  }
  const changed=new Set(edit.feature_ids||[]),oldFeatures=new Map(before.features.map(f=>[f.id,signature(f)]));
  for(const f of after.features)if(oldFeatures.get(f.id)!==signature(f))changed.add(f.id);
  for(const f of before.features)if(!after.features.some(row=>row.id===f.id))changed.add(f.id);
  const blockChanged=before.block.length!==after.block.length||before.block.width!==after.block.width||before.block.height!==after.block.height;
  const affected=new Set(blockChanged?[...automatic]:[...featureNetDependencies(before,[...changed]),...featureNetDependencies(after,[...changed])]);
  for(const n of after.nets||[])if(automatic.has(n.id)&&affected.has(n.id)){n.route_state='unresolved';n.route_issue='';n.routing_variant=null;}
  return edit.kind==='local'?{...edit,feature_ids:[...changed]}:{kind:'global',immediate:edit.immediate};
}

export function mergeVisibleRoutes(authored,proposal,{commit=false}={}){
  const result=structuredClone(authored),owners=owned(result),byNet=new Map(proposal.nets.map(n=>[n.id,n]));
  result.schema_version=proposal.schema_version||4;
  result.features=result.features.filter(f=>!owners.has(f.route_net));
  result.features.push(...structuredClone(proposal.features.filter(f=>owners.has(f.route_net))));
  for(const n of result.nets){
    if(!owners.has(n.id))continue;const source=byNet.get(n.id);if(!source)throw Error('Current route ownership is incomplete. Wait for routing to finish.');
    for(const key of ['routing_variant','route_state','route_issue','diameter'])n[key]=source[key];
    if(commit&&n.route_state==='proposal')n.route_state='committed';
  }
  return result;
}

export function requireVisibleRoutes(design){
  const missing=(design.nets||[]).filter(n=>n.routing==='automatic'&&(!n.route_state||n.route_state==='unresolved')&&(n.members||[]).length>1);
  if(missing.length)throw Error('Routing must finish for '+missing.map(n=>n.id).join(', ')+'. Inspect the current proposal, then Save or Validate.');
}
