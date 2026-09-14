// One newest snapshot. The server owns killable CAD workers; abort and explicit
// invalidation terminate obsolete work instead of merely discarding its result.
export function createPreviewQueue({post,onFast,onExact,onStatus,onError,cancelRemote=null,delay=350,exactDelay=450,timeout=20000}) {
  let latest=null,running=false,timer=null,version=0,cache=null,controller=null;
  const owner=globalThis.crypto?.randomUUID?.()||String(Math.random());
  function invalidate(){if(cancelRemote){controller?.abort();Promise.resolve(cancelRemote(owner,version)).catch(()=>{});}}
  async function request(url,job){
    const abort=controller=new AbortController();
    let timer;
    try{return await Promise.race([post(url,job.design,{signal:abort.signal,headers:{'X-PMC-Preview-Owner':owner,'X-PMC-Preview-Version':String(job.version)}}),new Promise((_,reject)=>{abort.signal.addEventListener('abort',()=>reject(Error('Preview superseded')),{once:true});timer=setTimeout(()=>{reject(Error('Exact preview exceeded the interactive time limit. Last usable view retained; retry or Save & Validate.'));abort.abort();if(cancelRemote)Promise.resolve(cancelRemote(owner,job.version)).catch(()=>{});},timeout);})]);}
    finally{clearTimeout(timer);if(controller===abort)controller=null;}
  }
  const current=job=>latest===job&&job.version===version;
  function arm(){clearTimeout(timer);if(!latest||running)return;timer=setTimeout(run,Math.max(0,latest.due-Date.now()));}
  async function run(){
    if(running||!latest)return;
    const job=latest;
    if(job.due>Date.now()){arm();return;}
    running=true;
    try{
      if(job.stage==='fast'){
        onStatus('routing');
        const result=await request('/api/preview',job);
        if(!current(job))return;
        onFast(result,job.design);
        job.stage='exact';job.due=Date.now()+exactDelay;onStatus('settling');
      }else{
        onStatus('exact');
        const result=await request('/api/preview-solid',job);
        if(!current(job))return;
        cache={key:job.key,result};latest=null;onExact(result,job.design);onStatus('ready');
      }
    }catch(error){if(current(job)){latest=null;onStatus('error');onError(error);}}
    finally{running=false;arm();}
  }
  return {
    schedule(design,scope=''){
      const snapshot=structuredClone(design),key=scope+JSON.stringify(snapshot);
      if(latest?.key===key)return;
      invalidate();++version;clearTimeout(timer);
      if(cache?.key===key){latest=null;onExact(cache.result,snapshot);onStatus('ready');return;}
      latest={design:snapshot,key,version,stage:'fast',due:Date.now()+delay};onStatus('queued');arm();
    },
    cancel(){invalidate();++version;latest=null;clearTimeout(timer);onStatus('idle');}
  };
}
