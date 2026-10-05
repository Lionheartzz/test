import {randomOwner} from './crypto-utils.js';
import {apiError} from './api-errors.js';
export const EXACT_PREVIEW_IDLE_MS=1500;
export const EXACT_PREVIEW_CLIENT_TIMEOUT_MS=185000;
// One newest snapshot. The server owns killable CAD workers; abort and explicit
// invalidation terminate obsolete work instead of merely discarding its result.
export function createPreviewQueue({post,stream=null,onFast,onExact,onStatus,onError,onProposal=()=>{},onTiming=()=>{},cancelRemote=null,delay=50,exactDelay=EXACT_PREVIEW_IDLE_MS,timeout=EXACT_PREVIEW_CLIENT_TIMEOUT_MS}) {
  let latest=null,running=false,timer=null,version=0,cache=null,controller=null;
  const owner=randomOwner();
  function invalidate(){
    if(!cancelRemote)return Promise.resolve();
    controller?.abort();
    clearTimeout(latest?.phaseTimer);
    const cancelledVersion=version;
    return Promise.resolve().then(()=>cancelRemote(owner,cancelledVersion)).catch(()=>{});
  }
  async function request(url,job,send=post){
    const abort=controller=new AbortController();
    let timer;
    try{return await Promise.race([send(url,job.design,{signal:abort.signal,preview:{scope:job.scope,context:job.context,exact_idle_ms:url==='/api/preview-solid'?Math.max(0,job.idleDue-Date.now()):0},headers:{'X-PMC-Preview-Owner':owner,'X-PMC-Preview-Version':String(job.version)}}),new Promise((_,reject)=>{abort.signal.addEventListener('abort',()=>reject(Error('Preview superseded')),{once:true});timer=setTimeout(()=>{reject(Error('Current exact preview timed out. Saved geometry is retained. Validate provides authoritative engineering results.'));abort.abort();if(cancelRemote)Promise.resolve(cancelRemote(owner,job.version)).catch(()=>{});},timeout);})]);}
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
      if(stream){
        onStatus('routing');
        const result=await request('/api/preview-solid',job,(_url,design,options)=>stream(design,{...options,onTiming:t=>{if(current(job))onTiming(t);},onProposal:p=>{if(current(job)){onProposal(p,job.design);if(!job.cached)onFast(p,job.design);onStatus('settling');job.phaseTimer=setTimeout(()=>{if(current(job))onStatus('exact');},Math.max(0,job.idleDue-Date.now()));}}}));
        if(!current(job))return;
        const context={owner,version:job.version,key:job.key};cache={key:job.key,result,context};latest=null;onExact(result,job.design,context);onStatus('ready');
      }else if(job.stage==='fast'){
        onStatus('routing');
        const result=await request('/api/preview',job);
        if(!current(job))return;
        onProposal(result,job.design);onFast(result,job.design);
        job.stage='exact';job.due=Date.now()+exactDelay;onStatus('settling');
      }else{
        onStatus('exact');
        const result=await request('/api/preview-solid',job);
        if(!current(job))return;
        const context={owner,version:job.version,key:job.key};cache={key:job.key,result,context};latest=null;onExact(result,job.design,context);onStatus('ready');
      }
    }catch(error){if(current(job)){latest=null;onStatus('error');onError(Error(apiError(error,job.design)));}}
    finally{clearTimeout(job.phaseTimer);running=false;arm();}
  }
  return {
    schedule(design,scope='',context=null,{immediate=false}={}){
      const idleDelay=immediate?0:exactDelay;
      const snapshot=structuredClone(design),seed=structuredClone(context),key=scope+JSON.stringify(snapshot)+(seed?JSON.stringify(seed):'');
      if(latest?.key===key)return;
      void invalidate();++version;clearTimeout(timer);
      if(cache?.key===key){
        // Repaint the cached exact core immediately, then re-establish the
        // server-owned preview context under this current owner/version.  The
        // previous version may already have been cancelled, so it must never
        // be reused for deferred layer requests.
        latest={design:snapshot,scope,context:seed,key,version,idleDue:Date.now()+idleDelay,stage:stream?'fast':'exact',due:Date.now(),cached:true};
        onExact(cache.result,snapshot,null);onStatus('ready');arm();return;
      }
      latest={design:snapshot,scope,context:seed,key,version,idleDue:Date.now()+idleDelay,stage:'fast',due:Date.now()+(immediate?0:delay)};onStatus('queued');arm();
    },
    cancel(){const cancelled=invalidate();++version;latest=null;clearTimeout(timer);onStatus('idle');return cancelled;}
  };
}
