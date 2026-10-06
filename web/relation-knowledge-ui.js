import {engineeringText,unitLabel} from './engineering-labels.js';

function sourceLink(element,parent,label,url){
  try{
    const parsed=new URL(url);if(!['http:','https:'].includes(parsed.protocol))return;
    const link=element('a',label);link.href=parsed.href;link.target='_blank';link.rel='noopener noreferrer';parent.append(link);
  }catch{}
}

// Read-only knowledge inside Cartridge detail. Never a placement/selection surface.
export async function relationKnowledgeUI(ctx,parent,cartridgeId,isCurrent){
  const {element,action,api}=ctx,root=element('section');parent.append(root);
  const technical=element('section'),relations=element('section');root.append(technical,relations);
  const current=()=>isCurrent()&&root.isConnected!==false;
  const technicalTask=(async()=>{
    try{
      const data=await api('/api/cartridges/'+encodeURIComponent(cartridgeId)+'/technical');if(!current())return;
      technical.append(element('h3','Technical Knowledge'));
      if(data.identity?.technical_record_present===false||data.identity?.disposition==='NOT_RESEARCHED'){
        technical.append(element('p','No technical record in current technical package'));return;
      }
      technical.append(element('p','Technical package record available. Relationship permissions are assessed separately.'));
      const details=element('details');details.append(element('summary',`Technical source observations · ${data.counts?.evidence||0}`));technical.append(details);
      for(const row of (data.values||[]).slice(0,20)){
        const raw=row.normalized_value??row.raw_value,value=['string','number','boolean'].includes(typeof raw)?engineeringText(String(raw)).slice(0,180):'Structured source observation';
        const line=element('div',null,'machining-summary');line.append(element('strong',row.property.replaceAll('_',' ')),element('p',`${value} ${row.normalized_unit||row.raw_unit||''}`));
        const original=row.original||{};if(original.evidence_text)line.append(element('p',engineeringText(original.evidence_text),'property-note'));
        sourceLink(element,line,original.source_title||'Source',original.source_url);details.append(line);
      }
    }catch{if(current())technical.append(element('p','Technical knowledge could not be loaded.'));}
  })();
  let offset=0,request=0;
  async function load(){
    const ticket=++request;
    try{
      const data=await api('/api/knowledge/cartridges/'+encodeURIComponent(cartridgeId)+'/cavities?'+new URLSearchParams({offset,limit:10}));
      if(!current()||ticket!==request)return;
      relations.replaceChildren(element('h3','Relationship evidence'));
      for(const row of data.items||[]){
        const item=element('section',null,'library-card');relations.append(item);
        item.append(element('h4',row.cavity_name_original||row.cavity_name),element('p',row.execution_eligible?'Execution-safe compatibility':'Reference evidence · no execution permission'),
          element('p',`${row.verification_status} · Confidence ${Number(row.confidence).toFixed(2)}`));
        for(const cavity of row.resolved_cavities||[])item.append(element('p',`${cavity.name} · ${unitLabel(cavity.unit_system)} · ${cavity.usable?'Geometry available':'Geometry incomplete'}`));
        for(const cavity of row.supplemental_cavities||[])item.append(element('p',`${cavity.display_name} · ${unitLabel(cavity.unit)} · Reference-only official cavity identity. Geometry not collected. Not selectable for machining / routing.`));
        if(row.resolution_status==='TYPE_MISMATCH')item.append(element('p','The referenced machining definition is an external port, not a cavity.'));
        else if(row.resolution_status==='UNRESOLVED_MASTER')item.append(element('p','Canonical cavity identity could not be fully resolved.'));
        item.append(element('p',[row.document_name,row.document_revision,row.page_number?'Page '+row.page_number:''].filter(Boolean).join(' · '),'property-note'),
          element('p',engineeringText(row.evidence_text),'property-note'));
        sourceLink(element,item,row.source_name||'Source',row.source_url);
      }
      if(!data.items?.length)relations.append(element('p','No relationship evidence in the current package.'));
      const paging=element('div',null,'action-row');relations.append(paging);
      if(offset)action(paging,'Previous evidence',()=>{offset=Math.max(0,offset-10);return load();});
      if(offset+10<data.total)action(paging,'Next evidence',()=>{offset+=10;return load();});
    }catch{if(current()&&ticket===request)relations.replaceChildren(element('p','Relationship evidence could not be loaded.'));}
  }
  await Promise.all([technicalTask,load()]);
}
