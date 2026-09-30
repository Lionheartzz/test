// Preview-only provenance. Never attached to or saved inside the authored draft.
const clone=value=>structuredClone(value);
const signature=value=>JSON.stringify(value);

export function featureNetDependencies(design,ids){
  const owners=new Set(ids);let changed=true;
  while(changed){changed=false;for(const f of design.features||[])if(owners.has(f.parent_id)&&!owners.has(f.id)){owners.add(f.id);changed=true;}}
  const nets=new Set();
  for(const f of design.features||[])if(owners.has(f.id)){
    if(f.circuit)nets.add(f.circuit);
    for(const net of Object.values(f.interface_nets||{}))if(net)nets.add(net);
  }
  for(const n of design.nets||[])if((n.members||[]).some(m=>owners.has(m.split(':')[0])))nets.add(n.id);
  return [...nets].sort();
}

export function previewEditForProperty(label,featureId){
  if(['Project name','Engineering material','Raw stock / standard blank'].includes(label))return {kind:'none'};
  if(featureId!=='block'&&['Face','Position U / mm','Position V / mm','Rotation / degrees'].includes(label))return {kind:'local',feature_ids:[featureId]};
  return {kind:'global'};
}

export function createPreviewRoutingState(){
  let seed=null,lastSignature=null,pending={kind:'global',feature_ids:[]},reason='no seed';
  const clear=(why='reset')=>{seed=null;lastSignature=null;pending={kind:'global',feature_ids:[]};reason=why;};
  return {
    clear,
    reason:()=>reason,
    accept(proposal,authored,scope){
      if(!proposal?.source_revision||!proposal.design)return clear();
      const variants=seed?.scope===scope?{...seed.variants}:{};
      for(const route of proposal.routes||[])if(route.variant&&route.variant!=='retained')variants[route.net]=route.variant;
      seed={scope,source:clone(authored),source_revision:proposal.source_revision,proposal:clone(proposal.design),variants};
      lastSignature=signature(authored);pending={kind:'none',feature_ids:[]};reason='matching current proposal';
    },
    edit(before,after,action,scope,{usable=true}={}){
      if(!usable)return clear('stale display');
      if(action.kind==='global')return clear('global edit');
      if(!seed)return clear('no previous proposal');
      if(seed.scope!==scope)return clear('different project scope');
      if(signature(before)!==lastSignature)return clear('draft changed without edit metadata');
      const ids=new Set(pending.feature_ids);
      for(const id of action.feature_ids||[])ids.add(id);
      pending={kind:pending.kind==='local'||action.kind==='local'?'local':'none',feature_ids:[...ids].sort()};
      lastSignature=signature(after);
    },
    context(scope){
      if(!seed||seed.scope!==scope)return null;
      const affected=new Set([...featureNetDependencies(seed.source,pending.feature_ids),...featureNetDependencies(JSON.parse(lastSignature),pending.feature_ids)]);
      return {...clone(seed),edit:{...clone(pending),affected_nets:[...affected].sort()}};
    },
    display(authored,scope){
      if(!seed||seed.scope!==scope)return authored;
      const ids=new Set((authored.features||[]).map(f=>f.id));
      return {...clone(authored),features:[...clone(authored.features),...clone(seed.proposal.features.filter(f=>f.route_net&&!ids.has(f.id)))]};
    }
  };
}
