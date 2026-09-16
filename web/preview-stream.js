// The server emits one early route proposal and one exact result for the same
// immutable draft. An error after headers is explicit, never a partial success.
export async function streamExactPreview(design,{onProposal,signal,headers}) {
  const response=await fetch('/api/preview-solid',{method:'POST',signal,
    headers:{'Content-Type':'application/json','X-PMC-Request':'local-console','Accept':'application/x-ndjson',...headers},body:JSON.stringify(design)});
  if(!response.ok){const body=await response.json();throw Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));}
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',exact;
  function event(line){
    if(!line.trim())return;
    const message=JSON.parse(line);
    if(message.type==='proposal')onProposal(message.result);
    else if(message.type==='exact')exact=message.result;
    else if(message.type==='error')throw Error(message.detail);
    else throw Error('Unrecognized exact preview event');
  }
  try{
    while(true){
      const {done,value}=await reader.read();buffer+=decoder.decode(value,{stream:!done});
      let end;while((end=buffer.indexOf('\n'))>=0){event(buffer.slice(0,end));buffer=buffer.slice(end+1);}
      if(done){if(buffer)event(buffer);break;}
    }
    if(!exact)throw Error('Exact preview stream ended before a usable result. Last usable view retained.');
    return exact;
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
