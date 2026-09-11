// Mirror schema-v1 legacy migration. Geometry shape never implies engineering use.
export function definitionRole(d){
  if(d.usage_role)return d.usage_role;
  const r=d.native?.record;
  return ['P','PORT'].includes(String(r?.cavity_type||r?.source_identity?.cavity_type||'').toUpperCase())?'external-port':'cartridge-cavity';
}
export const isCavity=d=>definitionRole(d)==='cartridge-cavity';
export const isPort=d=>definitionRole(d)==='external-port'&&d.zones.length===1&&!d.zones[0].offset_u&&!d.zones[0].offset_v;
export const nativeUnit=d=>d.native?.record?.unit_system||'';
