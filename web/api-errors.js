import {displayIdentity} from './presentation.js';
import {engineeringText} from './engineering-labels.js';

const fallback='The current edit is invalid. Restore the previous value or review the affected feature.';
export function boundedMessage(text,maximum=480){
  const value=String(text||'').replace(/\s+/g,' ').trim();
  return value.length>maximum?value.slice(0,maximum-1).trimEnd()+'…':value;
}

// Read only messages and locations. Pydantic input/context may contain the whole project.
export function apiError(value,design=null){
  const detail=value instanceof Error?value.message:value?.detail??value;
  if(Array.isArray(detail)){
    const meaningful=detail.filter(row=>row&&typeof row.msg==='string'&&!['missing','extra_forbidden','model_type','model_attributes_type'].includes(row.type));
    const nested=meaningful.filter(row=>(row.loc||[]).includes('design'));
    const rows=nested.length?nested:meaningful;
    const messages=[...new Set(rows.map(row=>{
      let message=userMessage(row.msg,design);
      const loc=row.loc||[],section=loc.findIndex(part=>['features','engravings','block_modifiers'].includes(part));
      const record=section>=0&&Number.isInteger(loc[section+1])?design?.[loc[section]]?.[loc[section+1]]:null;
      if(record&&!message.includes(objectName(record,design)))message=objectName(record,design)+': '+message;
      return message;
    }))];
    return boundedMessage(messages.slice(0,3).join(' ')||fallback);
  }
  return userMessage(typeof detail==='string'?detail:fallback,design);
}

export function objectName(row,design){
  if(row.kind==='rectangular-cutout')return 'Rectangular cutout';
  if(row.kind==='chamfer')return 'Chamfer';
  return displayIdentity(design,row.id);
}

export function userMessage(value,design=null,maximum=480){
  if(typeof value!=='string')return fallback;
  let message=value.trim();
  if(/Unexpected token|not valid JSON|Unexpected end of JSON/i.test(message))return 'The service returned an unreadable response. Retry the edit.';
  if(/^[\[{]/.test(message)){
    try{return boundedMessage(apiError(JSON.parse(message),design),maximum);}catch{return fallback;}
  }
  // A Python validation dump is never suitable UI text, even after truncation.
  if(/input_value=|input_type=|validation error/i.test(message)){
    const domain=message.match(/Value error,\s*([^\n]*?)(?:\s*\[type=|\n|$)/i);
    if(!domain)return fallback;message=domain[1];
  }
  if(/function-after\[|(?:['"]input['"]\s*:)|(?:['"]design['"]\s*:)|\b(?:Design|PreviewRequest)\(|body\.design|Traceback|^Field required$/i.test(message))return fallback;
  message=message.replace(/^Value error,\s*/i,'');
  const records=[...(design?.features||[]),...(design?.engravings||[]),...(design?.block_modifiers||[])].sort((a,b)=>b.id.length-a.id.length);
  for(const row of records){
    if(row.text&&message.includes(row.id))message=message.replace(/engraving origin is outside its block face/i,`is outside the ${row.face.replace(/^./,c=>c.toUpperCase())} face`);
    const escaped=row.id.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    message=message.replace(new RegExp('(?<![\\w-])'+escaped+'(?![\\w-])','g'),()=>objectName(row,design));
  }
  message=message.replace(/\b(?:ENG|MNT|BLK|PORT|DOC)_[0-9a-f]{12,32}\b/gi,token=>({ENG:'Engraving',MNT:'Mounting hole',BLK:'Block machining',PORT:'External port',DOC:'Project'})[token.split('_')[0].toUpperCase()])
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,'Engineering item')
    .replace(/engraving origin is outside its block face/i,'is outside its block face');
  return boundedMessage(engineeringText(message)||fallback,maximum);
}
