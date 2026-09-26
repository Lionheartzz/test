// Spatial references are allowed only for results bound to the displayed design.
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
