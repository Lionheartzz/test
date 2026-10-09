import {apiError} from './api-errors.js';
// The server emits one early route proposal and one exact result for the same
// immutable draft. An error after headers is explicit, never a partial success.
export async function streamExactPreview(design,{onProposal,onProgress=()=>{},onTiming=()=>{},signal,headers,preview=null}) {
  const started=performance.now();let parseMs=0,proposalMs=null,operationId=null;
  const response=await fetch('/api/preview-solid',{method:'POST',signal,
    headers:{'Content-Type':'application/json','X-PMC-Request':'local-console','Accept':'application/x-ndjson',...headers},body:JSON.stringify(preview?{design,...preview}:design)});
  const fetchMs=performance.now()-started;
  if(!response.ok){const body=await response.json().catch(()=>null);throw Error(apiError(body,design));}
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',exact;
  function event(line){
    if(!line.trim())return;
    const parseStarted=performance.now(),message=JSON.parse(line);parseMs+=performance.now()-parseStarted;
    if(message.type==='proposal'){proposalMs=performance.now()-started;onProposal(message.result);}
    else if(message.type==='progress'){
      operationId??=message.result.operation_id;
      if(message.result.operation_id===operationId)onProgress(message.result);
    }
    else if(message.type==='exact')exact=message.result;
    else if(message.type==='error')throw Error(apiError(message,design));
    else throw Error('Unrecognized exact preview event');
  }
  try{
    while(true){
      const {done,value}=await reader.read();buffer+=decoder.decode(value,{stream:!done});
      let end;while((end=buffer.indexOf('\n'))>=0){event(buffer.slice(0,end));buffer=buffer.slice(end+1);}
      if(done){if(buffer)event(buffer);break;}
    }
    if(!exact)throw Error('Exact preview stream ended before a usable result. Last usable view retained.');
    onTiming({kind:'preview-stream',fetch_ms:fetchMs,proposal_ms:proposalMs,exact_ms:performance.now()-started,parse_ms:parseMs});
    return exact;
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
