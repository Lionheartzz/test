// One in-flight request, one newest snapshot. Never abort a CAD request and
// immediately launch another: aborting fetch does not stop the server's OCCT job.
export function createPreviewQueue({post,onFast,onExact,onStatus,onError,delay=350,exactDelay=450}) {
  let latest=null,running=false,timer=null,version=0,cache=null;
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
        const result=await post('/api/preview',job.design);
        if(!current(job))return;
        onFast(result,job.design);
        job.stage='exact';job.due=Date.now()+exactDelay;onStatus('settling');
      }else{
        onStatus('exact');
        const result=await post('/api/preview-solid',job.design);
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
      ++version;clearTimeout(timer);
      if(cache?.key===key){latest=null;onExact(cache.result,snapshot);onStatus('ready');return;}
      latest={design:snapshot,key,version,stage:'fast',due:Date.now()+delay};onStatus('queued');arm();
    },
    cancel(){++version;latest=null;clearTimeout(timer);onStatus('idle');}
  };
}
