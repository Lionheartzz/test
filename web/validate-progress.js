import {uuidToken} from './crypto-utils.js';

const HISTORY_KEY='pmc.validate-timing.v1';
const matchEvent=(events,stage,candidate)=>[...(events||[])].reverse().find(e=>e.stage===stage&&e.candidate===candidate);

export function estimateRemaining(history,key,progress){
  const runs=history.filter(r=>r.key===key&&r.engine===progress.engine_revision).slice(-3);
  if(runs.length<2||progress.elapsed_s>Math.max(...runs.map(r=>r.seconds))*1.5)return null;
  const live=matchEvent(progress.events,progress.stage,progress.candidate);
  if(!live)return null;
  const spent=Math.max(0,progress.trace_elapsed_s-live.elapsed_s),remaining=[];
  for(const run of runs){
    const event=matchEvent(run.events,progress.stage,progress.candidate);
    if(!event)return null;
    remaining.push(run.trace_elapsed_s-event.elapsed_s-spent);
  }
  const conservative=Math.max(...remaining)*1.2;
  return conservative>0?Math.ceil(conservative/5)*5:null;
}

export function createValidationProgress({fetchStatus,render,getScope,storage,now=()=>performance.now(),
  schedule=(fn,ms)=>setTimeout(fn,ms),cancel=clearTimeout,idFactory=()=>uuidToken().replaceAll('-','')}){
  let active=null,shown=null,hideTimer=null,history=[];
  try{history=JSON.parse(storage?.getItem(HISTORY_KEY)||'[]').filter(r=>Number.isFinite(r.seconds)&&Array.isArray(r.events)).slice(-6);}catch{}
  const current=token=>active===token&&getScope()===token.scope;
  const elapsed=token=>Math.max(token.latest?.elapsed_s||0,(now()-token.started)/1000);
  function hide(token){if(shown===token){shown=null;render({visible:false});}}
  function paint(token){
    if(!current(token)){hide(token);return;}
    const p=token.latest||{},complete=token.complete;
    const recent=(p.events||[]).filter(e=>['alternate','step_verified'].includes(e.stage)).slice(-2);
    render({visible:true,operationId:token.id,percent:complete?100:token.percent,
      stage:complete?'Validation complete':p.state==='complete'?'Finalizing validation':p.stage_text||'Preparing design',
      detail:p.detail||'',elapsed:elapsed(token),eta:complete?null:estimateRemaining(history,token.key,p),
      estimating:!complete,substage:p.substage,recent:[...new Set(recent.map(e=>e.stage_text))]});
  }
  function stopPoll(token){token.finished=true;if(token.timer!=null)cancel(token.timer);token.controller?.abort();}
  async function poll(token){
    if(!current(token)||token.finished){hide(token);return;}
    token.controller=new AbortController();
    try{
      const result=await fetchStatus(token.id,token.projectId,{signal:token.controller.signal});
      if(!current(token)||token.finished)return;
      if(result.operation_id!==token.id||result.project_id!==token.projectId)return;
      token.latest=result;token.percent=Math.max(token.percent,Math.min(99,result.percent||0));
      if(result.state==='failed'){stopPoll(token);hide(token);return;}
    }catch{/* A missing/temporarily unreadable trace cannot cancel the build. */}
    finally{
      token.controller=null;
      if(current(token)&&!token.finished){paint(token);token.timer=schedule(()=>poll(token),400);}
      else if(!current(token))hide(token);
    }
  }
  async function run({projectId,scope,key,execute}){
    if(active)return null;
    if(hideTimer!=null)cancel(hideTimer);
    const token={id:idFactory(),projectId,scope,key,started:now(),percent:0,latest:null,finished:false};
    active=shown=token;paint(token);token.timer=schedule(()=>poll(token),400);
    try{
      const result=await execute(token.id);
      if(result.operation_id!==token.id)throw Error('Validate response does not match this operation. Reload project status.');
      stopPoll(token);token.complete=true;paint(token);
      try{
        const final=await fetchStatus(token.id,token.projectId,{signal:AbortSignal.timeout(2000)});
        if(final.operation_id===token.id&&final.project_id===token.projectId&&final.state==='complete'&&result.build?.counts?.FAIL===0){
          history.push({key:token.key,engine:final.engine_revision,seconds:final.elapsed_s,
            trace_elapsed_s:final.trace_elapsed_s,events:(final.events||[]).slice(-32)});
          history=history.slice(-6);try{storage?.setItem(HISTORY_KEY,JSON.stringify(history));}catch{}
        }
      }catch{}
      hideTimer=schedule(()=>hide(token),1200);
      return result;
    }catch(error){stopPoll(token);hide(token);throw error;}
    finally{if(active===token)active=null;}
  }
  return {run,pending:()=>!!active};
}

export function validationProgressUI(root){
  const node=name=>root.querySelector('[data-validate-'+name+']');
  return state=>{
    root.hidden=!state.visible;if(!state.visible)return;
    root.dataset.operationId=state.operationId;
    node('title').textContent=state.title||(state.percent===100?'Validation complete':'Validating manifold…');
    node('bar').value=state.percent;node('percent').textContent=Math.floor(state.percent)+'%';
    node('stage').textContent=state.stage;node('candidate').textContent=[state.detail,state.substage].filter(Boolean).join(' · ');
    node('recent').textContent=(state.recent||[]).join(' · ');
    node('time').textContent='Elapsed '+Math.floor(state.elapsed)+' s'+(state.eta!=null?' · about '+state.eta+' s remaining':state.estimating?' · Estimating remaining time…':'');
  };
}

// Preview and local generation share the Validate display and timing projection.
// A stationary milestone plus running indicator is intentional during one long
// native operation; elapsed seconds never manufacture a percentage.
export function calculationProgressUI(root,title){
  root.classList.add('calculation-progress');root.setAttribute('role','status');
  const node=(tag,key,cls)=>{const e=document.createElement(tag);e.dataset['validate'+key]=true;if(cls)e.className=cls;return e;};
  const heading=document.createElement('div');heading.className='validate-progress-heading';
  heading.append(node('strong','Title'),node('span','Percent'));
  const bar=node('progress','Bar');bar.max=100;bar.setAttribute('aria-label',title);
  root.replaceChildren(heading,bar,node('div','Stage','validate-progress-stage'),node('div','Time','validate-progress-time'),
    node('div','Candidate','validate-progress-detail'),node('div','Recent','validate-progress-recent'));
  const render=validationProgressUI(root);let operationId=null,percent=0;
  return progress=>{
    if(!progress){root.hidden=true;operationId=null;percent=0;return;}
    if(operationId!==progress.operation_id){operationId=progress.operation_id;percent=0;}
    percent=Math.max(percent,Math.min(99,progress.percent||0));
    root.setAttribute('aria-busy','true');
    const activity=[progress.completed_operations!=null?progress.completed_operations+' calculation steps completed':'',
      progress.cpu_s!=null?'Worker CPU '+Math.floor(progress.cpu_s)+' s':''].filter(Boolean).join(' · ');
    render({visible:true,operationId,percent,title,stage:progress.stage_text||'Preparing design',
      detail:[progress.layout?'Layout '+progress.layout+' of up to '+progress.layout_limit:'',progress.detail].filter(Boolean).join(' · '),
      substage:progress.substage,elapsed:progress.elapsed_s||0,estimating:false,recent:[activity,'Running · current proposal is not validated']});
  };
}
