export async function closureSelector(ctx,parent,feature,unit,isCurrent){
  const {element,field,api,change}=ctx;
  const box=element('section',null,'property-note');parent.append(box);
  box.append(element('p','Loading compatible closures…'));
  try{
    const data=await api('/api/closures/compatible?'+new URLSearchParams({diameter:feature.diameter,depth:feature.depth,unit}));
    if(!isCurrent()||box.isConnected===false)return;
    box.replaceChildren();
    const options={'':'Unresolved',...Object.fromEntries(data.items.map(row=>[row.id,row.display_name]))};
    const selectedId=data.items.find(row=>row.id===feature.closure_definition_id||row.aliases?.includes(feature.closure_definition_id))?.id||feature.closure_definition_id||'';
    const input=field(box,'Closure / Plug',selectedId,value=>change(()=>{
      feature.closure_definition_id=value||null;
      const row=data.items.find(item=>item.id===value);
      if(row){feature.plug_length=row.engagement_mm;feature.clearance_diameter=row.envelope.diameter_mm;feature.clearance_height=row.envelope.height_mm;}
      else if(feature.clearance_height===0)feature.clearance_height=20;
    }),options);
    if(!data.items.length){input.disabled=true;box.append(element('p','No compatible closure available.'))}
    else if(feature.closure_definition_id&&!data.items.some(row=>row.id===selectedId))box.append(element('p','Selected closure is not compatible.'));
    const selected=data.items.find(row=>row.id===selectedId);
    if(selected?.products?.length)box.append(element('p','Compatible products: '+selected.products.map(p=>`${p.manufacturer} ${p.part_number}`).join(', '),'property-note'));
  }catch{if(isCurrent()&&box.isConnected!==false)box.replaceChildren(element('p','Compatible closures could not be loaded.'));}
}
