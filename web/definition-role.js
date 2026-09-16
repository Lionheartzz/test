export function definitionRole(d){
  return d.kind==='external-port'?'external-port':'cartridge-cavity';
}
export const isCavity=d=>definitionRole(d)==='cartridge-cavity';
export const isPort=d=>definitionRole(d)==='external-port'&&d.zones.length===1&&!d.zones[0].offset_u&&!d.zones[0].offset_v;
export const nativeUnit=d=>d.unit_system||'';
