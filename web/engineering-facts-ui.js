const propertyLabel=name=>name.replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase());

// Only the central backend resolver determines applicability. This presentation
// never writes design fields or turns an evidence observation into an action.
export function engineeringFactsUI(ctx,parent,data,{title='Engineering data',evidence=null}={}){
  const {element,action}=ctx,box=element('section',null,'property-note');
  box.append(element('h4',title));parent.append(box);
  if(data?.identity){const i=data.identity;box.append(element('p',`${i.grade} · ${i.state} · ${i.standard}`));}
  const resolved=Object.values(data?.facts||{}).filter(f=>['SOURCE_BACKED','USER_OVERRIDE'].includes(f.status));
  for(const f of resolved)box.append(element('p',`${propertyLabel(f.property)}: ${f.value} ${f.unit||''} · ${f.status==='USER_OVERRIDE'?'User override':'Source-backed'}${f.condition?' · '+f.condition:''}`));
  if(data?.references?.length){const details=element('details');details.append(element('summary','Conditional/reference observations ('+data.references.length+')'));box.append(details);
    for(const f of data.references.slice(0,6))details.append(element('p',`${propertyLabel(f.property)}: ${f.value} ${f.unit||''} · Reference only · ${f.condition||f.reason}`));}
  if(!resolved.length&&!data?.references?.length)box.append(element('p','No resolved applicable technical values. Missing information remains unresolved.'));
  if(data&&!data.runtime_linked)box.append(element('p',data.identity?.reason||`Technical identity: ${data.disposition} · engineering facts unavailable`));
  if(evidence)action(box,'View technical evidence',evidence);
  return box;
}
