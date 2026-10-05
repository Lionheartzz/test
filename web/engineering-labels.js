// Presentation only: references and resolver state remain in the backing data.
const internalIdentity=/^(?:(?:cav|cart|thread|material|stock|tool|closure|modifier|technical|evidence|relation|batch|custom|legacy)_[A-Za-z0-9_-]+|(?:CV|PORT|DRILL|MNT|ENG|BLK)[_-][0-9a-f]{12,32}|[0-9a-f]{32,64}|C\d+(?:P\d+)?|EXT\d+)$/i;
export function engineeringName(value,fallback='Not specified'){return typeof value==='string'&&value.trim()&&!internalIdentity.test(value.trim())?value:fallback;}
export function engineeringText(value){return String(value??'').replace(/\b(?:cav|cart|thread|material|stock|tool|closure|modifier|technical|evidence|relation|batch|custom|legacy)_[A-Za-z0-9_-]+\b/gi,'selected item').replace(/\b[0-9a-f]{32,64}\b/gi,'selected item').replace(/\b(?:C\d+(?:P\d+)?|EXT\d+)\b/g,'connection').replace(/\bSQLite\b/gi,'engineering library').replace(/\bsource-backed\b/gi,'defined').replace(/\b(?:PARTIAL_CONFIRMED|RELATION_SOURCE_ONLY|FINAL_DISPOSITIONED|SOURCE_BACKED|LEGACY_OVERRIDE|execution_eligible|relation_only)\b/g,'').trim();}
export const unitLabel=value=>({metric:'Metric',inch:'Inch',custom:'Custom'})[value]||'—';
export const availability=row=>row.active===false||row.active===0?'Archived':row.usable===false||row.usable===0?'Machining definition incomplete':'Available';

export function machiningRecipe(ctx,parent,rows){
  const {element}=ctx;
  const names={kind:'Form',operation:'Operation',diameter:'Diameter',diameter_mm:'Diameter / mm',start:'Start / mm',end:'End / mm',depth:'Depth',depth_mm:'Depth / mm',end_diameter:'End diameter / mm',inner_diameter:'Inner diameter / mm',offset_u:'Offset U / mm',offset_v:'Offset V / mm',width:'Width / mm',width_mm:'Width / mm',height:'Height / mm',height_mm:'Height / mm',length:'Length / mm',length_mm:'Length / mm',radius:'Radius / mm',angle:'Angle / degrees',tool:'Cutter'};
  for(const [index,row]of (Array.isArray(rows)?rows:[]).entries()){const line=Object.entries(names).filter(([key])=>row[key]!==null&&row[key]!==undefined&&['string','number'].includes(typeof row[key])).map(([key,label])=>label+': '+engineeringName(String(row[key]),'Not specified'));if(line.length)parent.append(element('p',(index+1)+'. '+line.join(' · ')));}
}
