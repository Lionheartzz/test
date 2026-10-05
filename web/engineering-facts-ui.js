import {engineeringName,engineeringText} from './engineering-labels.js';
const propertyLabel=name=>name.replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase());
function factValue(value){
  if(typeof value==='number')return Number(value.toPrecision(6));
  if(typeof value==='boolean')return value?'Yes':'No';
  if(typeof value==='string')return engineeringText(engineeringName(value,'Not available'));
  if(Array.isArray(value)&&value.every(item=>typeof item==='number'))return value.join('–');
  if(value&&typeof value==='object'){const range=['minimum','min','maximum','max'].filter(key=>typeof value[key]==='number').map(key=>value[key]);if(range.length)return range.join('–');}
  return 'Not available';
}
// Applicability remains a backend decision; only engineering values render.
export function engineeringFactsUI(ctx,parent,data,{title='Engineering properties'}={}){
  const {element}=ctx,box=element('section',null,'property-note');box.append(element('h4',title));parent.append(box);
  if(data?.identity){const i=data.identity,designation=[i.grade,i.state,i.standard].filter(Boolean).join(' · ');if(designation)box.append(element('p',designation));}
  const resolved=Object.values(data?.facts||{}).filter(f=>['SOURCE_BACKED','USER_OVERRIDE'].includes(f.status));
  for(const fact of resolved)box.append(element('p',`${propertyLabel(fact.property)}: ${factValue(fact.value)} ${fact.unit||''}${fact.condition?' · '+engineeringText(fact.condition):''}`));
  if(!resolved.length)box.append(element('p','Engineering properties not available.'));
  return box;
}
