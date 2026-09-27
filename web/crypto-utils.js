// getRandomValues remains available in HTTP LAN contexts where randomUUID is hidden.
export function uuidToken(){
  const source=globalThis.crypto;
  if(source?.randomUUID)return source.randomUUID();
  if(!source?.getRandomValues)throw Error('Secure random IDs are unavailable in this browser.');
  const bytes=new Uint8Array(16);
  source.getRandomValues(bytes);
  bytes[6]=(bytes[6]&0x0f)|0x40;
  bytes[8]=(bytes[8]&0x3f)|0x80;
  const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

export function shortToken(){return uuidToken().replaceAll('-','').slice(0,12);}
export function randomOwner(){return uuidToken();}
