// Spatial references are allowed only for results bound to the displayed design.
import {displayFeatureName,displayNetName,displayRuleName} from './presentation.js';
// Check values remain authoritative in their report even when spatial references are stale.
export function reportSource({report,build,dirty,stale,externalChange,draftCheckedSignature,draftSignature,displayedDraftSignature,displayedSource,reportWasDraft=false}){
  if(!report)return {kind:'none',spatial:false,label:'Not validated'};
  if(draftCheckedSignature&&draftCheckedSignature===draftSignature&&displayedDraftSignature===draftSignature&&displayedSource!=='retained')
    return {kind:'draft',spatial:true,label:'Current draft exact checks · not saved'};
  const matched=!!build&&report.design_revision===build.design_revision&&report.engine_revision===build.engine_revision;
  if(matched&&!dirty&&!stale&&!externalChange&&displayedSource==='authoritative')
    return {kind:'authoritative',spatial:true,label:'Current authoritative build'};
  return {kind:'previous',spatial:false,label:reportWasDraft?'Previous draft exact checks · no current spatial mapping':'Previous build results · current objects are references only'};
}

export function resolveCheckTargets(check,{displayed,draft}={}){
  const features=displayed?.features||[];
  const available=new Set(features.filter(feature=>!feature.suppressed).map(feature=>feature.id));
  const ids=[];
  const add=id=>{if(available.has(id)&&!ids.includes(id))ids.push(id);};
  for(const raw of check?.items||[]){
    if(typeof raw!=='string')continue;
    if(raw==='block'){if(!ids.includes('block'))ids.push('block');continue;}
    const id=raw.split(':')[0];
    if(available.has(id)){add(id);continue;}
    // Network membership is explicit in the displayed design; names and colors are never identities.
    if(displayed?.nets?.some(net=>net.id===raw))for(const feature of features){
      if(feature.circuit===raw||feature.route_net===raw||feature.frozen_net===raw||Object.values(feature.interface_nets||{}).includes(raw))add(feature.id);
    }
    // Engineering review IDs may point to an explicit placement in the authored design.
    const review=draft?.review_items?.find(item=>item.id===raw);
    if(review?.placement_id)add(review.placement_id);
    if(typeof review?.subject==='string')add(review.subject.split(':')[0]);
    const component=draft?.schematic_intent?.components?.find(item=>item.id===raw);
    if(component?.placement_id)add(component.placement_id);
  }
  return {ids,primary:ids.find(id=>id!=='block')||ids[0]||null,secondary:ids.filter(id=>id!=='block').slice(1),unresolved:(check?.items||[]).filter(item=>item!=='block'&&!ids.includes(String(item).split(':')[0]))};
}

export function issueReferences(report,context){
  const byId=new Map();
  for(const check of report?.checks||[]){
    if(check.status==='PASS')continue;
    for(const id of resolveCheckTargets(check,context).ids){
      if(id==='block')continue;
      const row=byId.get(id)||{id,FAIL:0,WARNING:0};
      row[check.status]=(row[check.status]||0)+1;byId.set(id,row);
    }
  }
  return [...byId.values()];
}

export function groupRepairIssues(checks,design){
  const features=new Map((design?.features||[]).map(f=>[f.id,f])),groups=new Map();
  const netFor=item=>{const [id,zone]=String(item).split(':'),f=features.get(id);return zone?f?.interface_nets?.[zone]:f?.route_net||f?.frozen_net||f?.circuit;};
  for(const check of checks||[]){
    if(check.status!=='FAIL')continue;
    const ids=[...new Set((check.items||[]).map(item=>String(item).split(':')[0]).filter(id=>features.has(id)))].sort();
    const nets=[...new Set((check.items||[]).map(netFor).filter(Boolean))].sort();
    let family='engineering',title=displayRuleName(check.rule);
    if(['cavity_protected_region','port_protected_region'].includes(check.rule)){family='protected';title='Protected machining region';}
    else if(['circuit_intersection','declared_connection','unintended_cut_intersection','minimum_feature_wall'].includes(check.rule)){
      family='intersection';title=nets.length>1?'Hydraulic routes intersect / lack separation':'Machining contact needs correction';
    }else if(['connected_interface','circuit_connectivity','expected_connection','connection_opening_area'].includes(check.rule)){
      family='connection';title='Hydraulic connection needs correction';
    }else if(['plug_engagement','construction_closure','closure_entry_depth'].includes(check.rule)){family='plug';title='Construction closure conflict';}
    else if(['installation_access','boundary_access','component_boundary_clearance'].includes(check.rule)){family='access';title='Installation / service clearance';}
    const key=JSON.stringify([family==='engineering'?check.rule:family,family==='connection'&&nets.length===1?nets:ids.length?ids:check.items]);
    const row=groups.get(key)||{title,items:[],checks:[],nets:[],features:[]};
    row.items=[...new Set([...row.items,...(check.items||[])])];row.checks.push(check);
    row.nets=[...new Set([...row.nets,...nets])];row.features=[...new Set([...row.features,...ids])];groups.set(key,row);
  }
  return [...groups.values()].map(row=>({...row,
    label:row.title+(row.nets.length?' · '+row.nets.map(id=>displayNetName(design,id).replace(/^net_(?=[a-z])/i,'').replaceAll('_',' ')).join(' / '):''),
    objects:row.features.map(id=>displayFeatureName(features.get(id),design).replaceAll('_',' ')).join(' ↔ ')}));
}
