// Only normalized counts and fixed failure messages; never display provider bodies.
export const tokenLabels={input_tokens:'Input / prompt',output_tokens:'Output / completion',reasoning_tokens:'Reasoning (subset of output when reported)',cached_tokens:'Cached input (when reported)',total_tokens:'Total'};
export const available=value=>value===null||value===undefined?'Unavailable':String(value);
export function attemptStatus(run){return !run?'Not analyzed':run.status==='failed'?'Last analysis failed · '+(run.error||'PROVIDER_FAILED'):'Last analysis · '+run.status;}
export function runDiagnostics(parent,run,{element}){
  const box=element('section',null,'ai-run-diagnostics');box.setAttribute('aria-label','Analysis run diagnostics');parent.append(box);
  box.append(element('h3',run.status==='failed'?'Last analysis failed · '+(run.error||'PROVIDER_FAILED'):'Analysis '+run.status),
    element('p',`${run.provider.id} / ${run.provider.model} · ${run.latency_ms==null?'Duration unavailable':(run.latency_ms/1000).toFixed(2)+' s'} · ${run.created_at||''}`));
  if(run.error_message)box.append(element('p',run.error_message,'ai-failure-help'));
  else if(run.error)box.append(element('p','This historical attempt failed. Inputs and prior successful results are retained. Open Provider settings to review reasoning, output budget and timeout.'));
  const d=run.diagnostics;
  box.append(element('p',`Stage: ${run.phase||d?.phase||'Unavailable (historical run)'} · Requests: ${available(d?.request_count)} · Retries: ${available(d?.retry_count)}`));
  const table=element('table',null,'check-table'),head=element('tr');
  for(const title of ['Token usage','All requests','Reported subtotal'])head.append(element('th',title));table.append(head);
  for(const [key,label]of Object.entries(tokenLabels)){const row=element('tr');for(const cell of [label,available(run.usage?.[key]),available(d?.reported_usage?.[key])])row.append(element('td',cell));table.append(row);}box.append(table);
  box.append(element('p','Unavailable means not reported or incomplete, not zero. Subtotals may include partial usage and exclude unreported attempts; they can understate billing. Reasoning/cached tokens are not added to totals.','property-note'));
  if(!d){box.append(element('p','Detailed usage, request count and failure stage were not recorded by the earlier adapter. They cannot be reconstructed from this run.','property-note'));return;}
  const detail=element('details');detail.open=d.attempts.some(a=>a.validation_errors?.length);detail.append(element('summary','Request settings and per-attempt diagnostics'));box.append(detail);
  detail.append(element('p',`Task: ${d.operation} · Reasoning dialect: ${d.reasoning.dialect} · Mode: ${d.reasoning.mode} · Effort: ${d.reasoning.effort} · Control: ${d.reasoning_control}`),
    element('p',`${d.max_tokens_parameter}: ${d.max_tokens==null?'Omitted — provider default':d.max_tokens} · Provider deadline: ${d.timeout_seconds} s · Streaming: ${d.stream?'yes':'no'}`),
    element('p',`Prompt: ${d.prompt_revision} · ${d.text_chars} text characters · ${d.schema_chars} schema characters · ${d.image_count} page images · ${d.image_bytes} image bytes`));
  for(const warning of d.control_warnings||[])detail.append(element('p',({reasoning_dialect_required:'Reasoning controls were not sent: choose a parameter dialect supported by your endpoint.',effort_required:'This dialect needs an explicit effort to enable reasoning; enable control was not sent.',effort_ignored_when_disabled:'Effort was omitted because thinking is disabled.',provider_may_ignore_controls:'Controls were requested. PMC cannot verify that this provider/model honored them; inspect reported reasoning usage.'})[warning]));
  for(const a of d.attempts){const card=element('section',null,'library-card');detail.append(card);card.append(element('strong',`Request ${a.index} · ${a.status}${a.error?' · '+a.error:''}`),
    element('p',`${a.phase} · ${(a.latency_ms/1000).toFixed(2)} s · HTTP ${available(a.http_status)} · Finish: ${available(a.finish_reason)}${a.rejected_parameter?' · Rejected parameter: '+a.rejected_parameter:''}`),
    element('p',Object.entries(tokenLabels).map(([key,label])=>label+': '+available(a.usage[key])).join(' · ')),
    element('p',`Usage: ${a.usage_final?'final reported snapshot':a.usage_reported?'partial reported snapshot':'unavailable'} · Response bytes: ${a.response_bytes} · Final content characters: ${a.content_chars} · Reasoning characters: ${a.reasoning_chars} · Validation errors: ${available(a.validation_error_count)}`));
    for(const e of a.validation_errors||[]){const path=e.path.reduce((s,p)=>s+(typeof p==='number'?`[${p}]`:'.'+p),'$');const item=element('div',null,'ai-validation-detail');item.append(element('strong',path+' · '+e.type),element('p',e.explanation),element('p',`${e.classification} · ${e.action}${e.path_redacted?' · Unknown field name redacted':''}`,'property-note'));card.append(item);}
    if(a.validation_error_count&&!a.validation_errors?.length)card.append(element('p','Field-level errors were not recorded for this historical attempt and cannot be reconstructed.'));
  }
}
