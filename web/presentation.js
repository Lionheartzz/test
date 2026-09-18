const faceOrder={left:0,right:1,front:2,back:3,bottom:4,top:5};

export function displayNetName(design,netId){
  return design?.nets?.find(net=>net.id===netId)?.label||netId||'Unassigned';
}

function stableFeatureOrder(a,b){
  return (faceOrder[a.face]??99)-(faceOrder[b.face]??99)||
    (a.u??0)-(b.u??0)||(a.v??0)-(b.v??0)||(a.depth??0)-(b.depth??0)||String(a.id).localeCompare(String(b.id));
}

export function displayExternalPortName(feature,design){
  if(feature.schematic_id)return feature.schematic_id;
  if(feature.id&&!String(feature.id).startsWith('PORT_'))return feature.id;
  const peers=(design?.features||[]).filter(item=>item.kind==='port'&&item.circuit===feature.circuit&&!item.suppressed).sort(stableFeatureOrder);
  const net=displayNetName(design,feature.circuit),index=peers.findIndex(item=>item.id===feature.id);
  return peers.length<=1?net:`${net}${Math.max(0,index)+1}`;
}

export function displayInterfaceName(design,featureId,interfaceId,{definitionOnly=false,index=null}={}){
  const feature=(design?.features||[]).find(item=>item.id===featureId);
  const net=feature?.interface_nets?.[interfaceId];
  if(feature&&net)return `${displayFeatureName(feature,design)}-${displayNetName(design,net)}`;
  const n=index??Math.max(0,Object.keys(feature?.interface_nets||{}).indexOf(interfaceId));
  return definitionOnly?`Interface ${n+1} · ${interfaceId}`:`${displayFeatureName(feature||{id:featureId,kind:'cavity'},design)} · Interface ${n+1}`;
}

export function displayRouteName(feature,design){
  const netId=feature.route_net||feature.frozen_net;
  if(feature.kind!=='drilling'||!netId)return null;
  const features=design?.features||[];
  const route=features.filter(item=>item.kind==='drilling'&&(item.route_net||item.frozen_net)===netId).sort(stableFeatureOrder);
  const referencedOwners=new Set(route.flatMap(item=>item.connects_to||[]).filter(value=>String(value).includes(':')).map(value=>String(value).split(':')[0]));
  const owners=features.filter(item=>item.kind==='cavity'&&!item.suppressed&&(Object.values(item.interface_nets||{}).includes(netId)||referencedOwners.has(item.id))).sort(stableFeatureOrder);
  const prefix=owners.length===1?`${displayFeatureName(owners[0],design)}-${displayNetName(design,netId)}`:displayNetName(design,netId);
  return `${prefix}${Math.max(0,route.findIndex(item=>item.id===feature.id))+1}`;
}

export function displayFeatureName(feature,design){
  if(!feature)return 'Unknown feature';
  const route=displayRouteName(feature,design);if(route)return route+(feature.plugged?' · PLUG':'');
  if(feature.kind==='port')return displayExternalPortName(feature,design);
  return design?.schematic_intent?.components?.find(component=>component.placement_id===feature.id)?.label||feature.id;
}

export function displayMemberName(design,member){
  const text=String(member||'');
  const split=text.indexOf(':');
  if(split>0){
    const owner=text.slice(0,split),suffix=text.slice(split+1);
    const feature=(design?.features||[]).find(item=>item.id===owner);
    if(feature?.kind==='cavity')return displayInterfaceName(design,owner,suffix);
  }
  const feature=(design?.features||[]).find(item=>item.id===text);
  return feature?displayFeatureName(feature,design):text;
}

const ruleNames={
  engineering_review:'Engineering review',schematic_conformance:'Schematic conformance',
  cartridge_compatibility:'Cartridge compatibility',connected_interface:'Hydraulic interface connection',
  circuit_connectivity:'Hydraulic net connectivity',minimum_feature_wall:'Minimum feature wall',
  external_wall:'External wall',solid_validity:'Solid validity',solid_count:'Solid count',
  step_round_trip:'STEP round trip',cavity_collision:'Cavity collision',pressure_strength:'Pressure strength'
};
export function displayRuleName(rule){return ruleNames[rule]||String(rule||'').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());}

export function displayReviewName(value){
  const text=String(value||'');
  if(text==='PORT_SPEC')return 'External port specification';
  if(text==='External ports')return 'External ports';
  return text.startsWith('REVIEW_')?'Engineering review item':text;
}

export function displayIdentity(design,value){
  let text=String(value??'');
  if(text.startsWith('F:'))text=text.slice(2).split(':step:')[0];
  const feature=(design?.features||[]).find(item=>item.id===text);
  if(feature)return displayFeatureName(feature,design);
  const split=text.indexOf(':');
  if(split>0){
    const owner=text.slice(0,split),suffix=text.slice(split+1);
    const placed=(design?.features||[]).find(item=>item.id===owner);
    if(placed?.kind==='cavity')return displayInterfaceName(design,owner,suffix);
  }
  return displayReviewName(text);
}
