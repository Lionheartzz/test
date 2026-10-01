// Read-only research presentation. No placement, binding or design-state hooks.
export function sourceLink(ctx,parent,value){
  if(typeof value!=='string'||!/^[Hh][Tt][Tt][Pp][Ss]?:\/\/[^/\s]/.test(value)||/\s/.test(value))return;
  try{const url=new URL(value);if(!['http:','https:'].includes(url.protocol)||!url.hostname||url.username||url.password)return;
    const link=ctx.element('a','Open source');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';parent.append(link);
  }catch{/* A local artifact or an incomplete address remains plain provenance. */}
}

const labels={maximum_flow:'Maximum Flow',capacity:'Capacity',nominal_capacity:'Nominal Capacity',rated_flow:'Rated Flow',nominal_flow:'Nominal Flow',maximum_working_pressure:'Maximum Working Pressure',rated_pressure:'Rated Pressure'};
export const propertyLabel=name=>labels[name]||name.replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase());
function sectionFor(property,material){
  if(material){
    if(/strength|hardness|elongation|modulus|fatigue|poisson|shear/.test(property))return 'Mechanical Properties';
    if(/machin|corrosion|weld|workability|braze/.test(property))return 'Machinability / Corrosion / Weldability';
    return 'Thermal / Engineering Properties';
  }
  if(/pressure|flow|capacity|leakage|pilot|control_ratio|crack/.test(property))return 'Hydraulic Performance';
  if(/torque|weight|length|hex|wrench|dimension|thread/.test(property))return 'Installation & Mechanical';
  if(/fluid|temperature|viscosity|filtration|cleanliness/.test(property))return 'Fluid & Temperature';
  if(/seal/.test(property))return 'Seals';
  if(/coil|current|voltage|power|duty|connector|override|PWM|pwm|dither|electrical/.test(property))return 'Electrical / Solenoid';
  if(/datasheet|catalog|CAD|cad|document|product_status/.test(property))return 'Documentation & CAD';
  return 'Technical Summary';
}

export function technicalKnowledgeUI(ctx,parent,data,base,isCurrent,{material=false}={}){
  const {element,action,field,api}=ctx;
  const box=(title,host=parent)=>{const node=element('section',null,'library-card');node.append(element('h3',title));host.append(node);return node;};
  const identity=box(material?'Identity / Grade / Standard':'Technical Knowledge · Identity'),record=data.identity;
  identity.append(element('p',`${record.full_part_number||record.id} · Base: ${record.base_model||'Not established'} · ${record.disposition}`),element('p',material?`Research disposition: ${record.disposition}; condition and form limits retained.`:`Research stage: ${record.research_stage||'Not researched'}`));
  if(record.disposition==='IDENTITY_AMBIGUOUS')identity.append(element('p','Identity attribution is unresolved. Technical values are not automatically inherited from a similar model.','warning'));
  if(record.disposition==='RELATION_SOURCE_ONLY')identity.append(element('p','Exact technical parameter evidence was not established in this research pass. Relationship evidence remains available.','warning'));
  if(record.disposition==='PARTIAL_CONFIRMED'&&data.counts.evidence===0)identity.append(element('p','Research disposition is preserved, but no evidence is explicitly attributed to this stored manufacturer and code. Similar manufacturer records have not been inherited.','warning'));
  identity.append(element('p',`${data.counts.evidence} evidence records · ${data.counts.sources} sources · ${data.counts.conflicts} conflicts. Research knowledge does not grant execution permission.`));
  if(material){const original=record.original;identity.append(element('p',`Standard: ${original.standard||'Not reported'} · Condition: ${original.temper_condition||'Not reported'} · Form: ${original.product_form||'Not reported'}`),element('p',`Aliases: ${(original.aliases||[]).join(', ')||'None established'}`));}
  const sections=new Map(),seen=new Set();
  const normalized=row=>row.normalized_value!==null&&row.normalized_value!==undefined&&row.normalized_value!==''?`${typeof row.normalized_value==='string'?row.normalized_value:JSON.stringify(row.normalized_value)} ${row.normalized_unit||''}`:'';
  for(const row of data.values){
    const key=JSON.stringify([row.property,row.raw_value,row.raw_unit,row.scope,row.condition,row.applicable_option,row.status]);if(seen.has(key))continue;seen.add(key);
    const title=sectionFor(row.property,material);if(!sections.has(title))sections.set(title,box(title));const host=sections.get(title);
    host.append(element('p',`${propertyLabel(row.property)}: ${row.raw_value} ${row.raw_unit||''}`),element('p',`${row.scope} · ${row.status}${row.condition?' · '+row.condition:''}${row.applicable_option?' · Option: '+row.applicable_option:''}`));
    if(normalized(row))host.append(element('p','Normalized: '+normalized(row)));
    if(row.scope_original&&row.scope_original!==row.scope)host.append(element('p','Original source scope: '+row.scope_original));
  }
  if(data.values_total>data.values.length)parent.append(element('p',`Showing ${data.values.length} of ${data.values_total} sourced values. Filter and page through Evidence to inspect the remaining values.`));
  if(data.field_status.length){const host=box('Field research outcomes');for(const row of data.field_status)host.append(element('p',`${propertyLabel(row.field_group)}: ${row.status}`));}
  function evidenceCard(host,row){
    const raw=row.original||{},card=box(`${propertyLabel(row.property)} · ${row.evidence_class}`,host);
    card.append(element('p',`${row.raw_value} ${row.raw_unit||''}`),element('p',`${row.scope} · ${row.condition||'Condition not reported'}${row.applicable_option?' · Option: '+row.applicable_option:''}`));
    if(normalized(row))card.append(element('p','Normalized: '+normalized(row)));
    if(row.scope_original&&row.scope_original!==row.scope)card.append(element('p','Original scope: '+row.scope_original));
    if(row.evidence_class==='source_review')card.append(element('p','Source registry inspection; this record does not assert a technical parameter.','warning'));
    card.append(element('p',`${raw.source_title||raw.source_author||'Source title not reported'} · ${raw.revision||raw.publication_date||'Revision/date not reported'} · Page: ${raw.page_number??'Not reported'} · Confidence: ${raw.confidence??'Not reported'}`),element('p',raw.evidence_text||raw.disposition_note||'Evidence text not provided'));
    sourceLink(ctx,card,raw.source_url);for(const source of row.sources||[])if(source.url!==raw.source_url){card.append(element('p',source.title));sourceLink(ctx,card,source.url);}
    card.append(element('p','Evidence ID: '+(raw.evidence_id||row.id)));
  }
  function paged(host,title,path,render,filter=false){
    const controls=element('div',null,'action-row'),list=element('div'),pager=element('div',null,'action-row');host.append(controls,list,pager);
    let offset=0,property='',request=0;
    const load=async(reset=false)=>{if(reset)offset=0;const current=++request;try{const result=await api(base+path+'?'+new URLSearchParams({offset,limit:20,...(filter?{property}:{})}));if(!isCurrent()||current!==request)return;if(reset)list.replaceChildren();for(const row of result.items)render(list,row);offset+=result.items.length;pager.replaceChildren(element('p',`${offset} / ${result.total} ${title}`));if(offset<result.total)action(pager,'More '+title,()=>load());}catch(error){if(isCurrent()&&current===request)pager.replaceChildren(element('p',title+' could not load: '+error.message,'error'));}};
    if(filter)field(controls,'Evidence property',property,value=>{property=value;load(true);});
    action(controls,'Load '+title,()=>load(true));
  }
  if(data.counts.conflicts){const host=box('Conflicts');host.append(element('p',`${data.counts.conflicts} registered conflicts. No unresolved winner is selected.`));
    paged(host,'technical conflicts','/conflicts',(list,row)=>{const card=box(`${row.conflict_type} · ${propertyLabel(row.property)}`,list);card.append(element('p',row.resolution),element('p',row.link_status));for(const side of ['a','b']){card.append(element('h4',`Evidence ${side.toUpperCase()} · ${row.sides[side].total} links`),element('p',row.original['evidence_'+side]||''));for(const evidence of row.sides[side].items)evidenceCard(card,evidence);}if(row.preferred_evidence_id)card.append(element('p','Explicit preferred evidence: '+row.preferred_evidence_id));});
  }
  const evidence=box('Technical Evidence');paged(evidence,'technical evidence','/evidence',evidenceCard,true);
  if(material){
    if(data.surface_treatments.length){const host=box('Surface Treatments');for(const row of data.surface_treatments){const card=box(`${row.treatment} · ${row.status}`,host);for(const [label,value] of Object.entries(row))if(value&&label!=='treatment'&&label!=='status')card.append(element('p',`${propertyLabel(label)}: ${value}`));}}
    const stock=box('Engineering Stock');stock.append(element('p',data.engineering_stock.length?'Executable engineering stock definitions':'No runtime stock is linked to this research grade.'));
    for(const row of data.engineering_stock)stock.append(element('p',`${row.unit_system} · ${row.size_1_mm} × ${row.size_2_mm} mm · allowance ${row.allowance_1_mm} × ${row.allowance_2_mm} mm · ${row.active?'Active':'Archived'}`));
    const supplier=box('Supplier / Research Stock Evidence');supplier.append(element('p',`${data.supplier_stock_count} listings. Supplier listings are separate from engineering stock; dated seller availability is not current inventory.`));
    paged(supplier,'supplier listings','/stock',(list,row)=>{const raw=row.original,card=box(`${raw.supplier} · ${raw.material} · ${row.availability}`,list);card.append(element('p',`${raw.product_form} · ${[raw.width,raw.height,raw.length].filter(Boolean).join(' × ')}${raw.diameter?' · Ø '+raw.diameter:''} ${raw.unit}`),element('p',raw.notes),element('p','Retrieved: '+raw.retrieved_date));sourceLink(ctx,card,raw.source_url);});
  }
}
