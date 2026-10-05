// Transient request ownership. Only an explicitly current proposal can be saved.
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
    current(authored,scope){return seed&&seed.scope===scope&&pending.kind==='none'&&signature(authored)===lastSignature?clone(seed.proposal):null;},
    acceptExact(result,authored,scope){
      if(seed&&seed.scope===scope&&pending.kind==='none'&&signature(authored)===lastSignature)seed.proposal.features=clone(result.features);
    },
    seedCommitted(design,scope,sourceRevision){
      if((design.nets||[]).some(n=>n.routing==='automatic'&&(!n.route_state||n.route_state==='unresolved')))return clear('uncommitted project');
      seed={scope,source:clone(design),source_revision:sourceRevision,proposal:clone(design),variants:Object.fromEntries((design.nets||[]).filter(n=>n.routing_variant).map(n=>[n.id,n.routing_variant]))};
      lastSignature=signature(design);pending={kind:'none',feature_ids:[]};reason='saved geometry';
    },
    accept(proposal,authored,scope,currentAuthored=authored){
      if(!proposal?.source_revision||!proposal.design)return clear();
      const variants=seed?.scope===scope?{...seed.variants}:{};
      for(const route of proposal.routes||[])if(route.variant&&route.variant!=='retained')variants[route.net]=route.variant;
      seed={scope,source:clone(authored),source_revision:proposal.source_revision,proposal:clone(proposal.design),variants};
      lastSignature=signature(currentAuthored);pending={kind:'none',feature_ids:[]};reason='matching current proposal';
    },
    edit(before,after,action,scope,{usable=true}={}){
      if(!usable)return clear('stale display');
      if(action.kind==='global')return clear('explicit geometry/routing edit');
      if(!seed)return clear('no previous proposal');
      if(seed.scope!==scope)return clear('different project scope');
      if(signature(before)!==lastSignature)return clear('draft changed without edit metadata');
      if(action.kind==='none')for(const net of after.nets||[]){
        if(net.route_state==='stale'){const stored=seed.proposal.nets.find(n=>n.id===net.id);if(stored){stored.route_state='stale';stored.route_issue=net.route_issue;}}
      }
      const ids=new Set(pending.feature_ids);
      for(const id of action.feature_ids||[])ids.add(id);
      pending={...pending,...action,kind:action.kind==='conditions'||pending.kind==='conditions'?'conditions':pending.kind==='local'||action.kind==='local'?'local':'none',
        affected_nets:[...new Set([...(pending.affected_nets||[]),...(action.affected_nets||[])])].sort(),
        resize_nets:[...new Set([...(pending.resize_nets||[]),...(action.resize_nets||[])])].sort(),feature_ids:[...ids].sort()};
      lastSignature=signature(after);
    },
    context(scope){
      if(!seed||seed.scope!==scope||!seed.source_revision)return null;
      const affected=new Set([...featureNetDependencies(seed.source,pending.feature_ids),...featureNetDependencies(JSON.parse(lastSignature),pending.feature_ids)]);
      return {...clone(seed),edit:{kind:pending.kind,feature_ids:[...pending.feature_ids],affected_nets:pending.kind==='conditions'?pending.affected_nets:[...affected].sort(),resize_nets:pending.resize_nets||[]}};
    },
    display(authored,scope){
      if(!seed||seed.scope!==scope)return authored;
      const automatic=new Set((authored.nets||[]).filter(n=>n.routing==='automatic').map(n=>n.id));
      return {...clone(authored),features:[...clone(authored.features.filter(f=>!automatic.has(f.route_net))),...clone(seed.proposal.features.filter(f=>automatic.has(f.route_net)))]};
    }
  };
}
