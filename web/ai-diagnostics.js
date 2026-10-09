export const tokenLabels={input_tokens:'Input',output_tokens:'Output',reasoning_tokens:'Reasoning',cached_tokens:'Cached input',total_tokens:'Total'};
export const available=value=>value==null?'Unavailable':String(value);
export function attemptStatus(run){return !run?'Not analyzed':run.status==='failed'?'Last analysis failed':run.status==='completed'?'Analysis complete':'Analysis in progress';}
const failureReasons={PROVIDER_TIMEOUT:'The provider timed out. Review the timeout setting or try again later.',PROVIDER_AUTH:'The provider could not authenticate. Check Provider Settings.',PROVIDER_RATE_LIMIT:'The provider is busy or its quota has been reached. Try again later.',PROVIDER_NETWORK:'The provider could not be reached. Check the connection and Provider Settings.',PROVIDER_OUTPUT_TRUNCATED:'The analysis response was incomplete. Review the output limit in Provider Settings.',INVALID_STRUCTURED_OUTPUT:'The analysis response could not be read. Review the schematic and provider output settings.'};
const normalizationReasons={source_document_invalid:'The schematic document reference is missing or invalid.',source_page_invalid:'The schematic page reference is missing or invalid.',user_quote_not_exact:'A requirement quote did not exactly match the original input.',topology_normalization_invalid:'Hydraulic connections could not be interpreted. Review the schematic.',requirement_normalization_invalid:'An engineering requirement could not be interpreted. Review the original requirement.',other_normalization_error:'The observations could not be interpreted safely. Review the inputs.'};
function locationLabel(value){const match=/^(requirements|components|external_ports)\[(\d{1,3})\](?:\.ports\[(\d{1,3})\])?$/.exec(value||'');if(!match)return '';return ({requirements:'Requirement',components:'Component',external_ports:'External port'})[match[1]]+' '+(Number(match[2])+1)+(match[3]===undefined?'':', port '+(Number(match[3])+1));}
const observationReasons={
  'Unknown observations must have a null value. Do not assert a value while marking it unknown.':'The provider marked an observation as unknown but also supplied a value. This does not establish a confirmed engineering fact.',
  'A clear observation requires a non-null value. If the source is unclear, preserve uncertainty instead of inventing a value.':'The provider marked an observation as clear without supplying a value.',
  'A non-null value needs schematic/user provenance or explicit AI-inference provenance; unknown provenance cannot support an asserted value.':'The provider supplied a value without an identifiable source. It cannot be treated as an engineering fact.',
  'Labels must be unique within the component or external-port group; do not merge distinct hydraulic entities to resolve this.':'The response contains duplicate component or port labels. Distinct hydraulic items need separate labels.',
  'A net name must be nonempty text or null. Do not invent a connection for an unknown net.':'A hydraulic connection has an invalid or empty net name.',
  'A connected hydraulic port has no net assignment. Resolve the connection from the schematic; do not invent a net.':'The response describes a connected port without identifying its hydraulic connection.',
  'A blocked or terminated port also has a net assignment. Resolve the conflicting connection from the schematic.':'The response describes the same port as blocked or terminated and connected to a hydraulic net.'
};
const fieldLabels={manufacturer:'Manufacturer',model:'Model',cavity:'Cavity',mounting_interface:'Mounting interface',functional_type:'Function',net:'Hydraulic connection',label:'Label',specification:'Port specification',source:'Observation source',document:'Schematic document',page:'Schematic page',quote:'Source quote'};
function validationFailure(attempt){
  const errors=(attempt?.validation_errors||[]).filter(error=>error.action!=='normalized');
  if(!errors.length)return null;
  const error=errors[0],path=Array.isArray(error.path)?error.path:[];
  let location='';
  if(['components','external_ports','requirements'].includes(path[0])&&Number.isInteger(path[1])&&path[1]>=0&&path[1]<1000){
    let value=path[0]+'['+path[1]+']';
    if(path[0]==='components'&&path[2]==='ports'&&Number.isInteger(path[3])&&path[3]>=0&&path[3]<1000)value+='.ports['+path[3]+']';
    location=locationLabel(value);
  }
  const field=fieldLabels[path.at(-1)];if(field)location+=(location?' · ':'')+field;
  let message=observationReasons[error.explanation];
  if(!message){
    if(error.type==='json_invalid')message='The provider returned invalid JSON. The response could not be interpreted.';
    else if(error.type==='missing')message=path.includes('ports')||path.includes('net')?'The response omitted a required hydraulic field.':'The response omitted a required field.';
    else if(error.type==='literal_error'&&path.includes('source')&&path.at(-1)==='kind')message='The response uses an unsupported observation source.';
    else message=error.classification==='semantic'?'A schematic observation failed the consistency checks. Review the affected item before retrying.':'A response field does not match the required format. Review the affected item before retrying.';
  }
  return {message,location,more:errors.length>1};
}
export function runDiagnostics(parent,run,{element}){
  const box=element('section',null,'ai-run-diagnostics');box.setAttribute('aria-label','Analysis result');parent.append(box);box.append(element('h3',attemptStatus(run)));
  if(run.provider?.model)box.append(element('p','Model: '+run.provider.model));if(run.latency_ms!=null)box.append(element('p','Elapsed: '+(run.latency_ms/1000).toFixed(1)+' s'));
  if(run.status!=='failed')return;
  const attempt=run.diagnostics?.attempts?.at(-1),issue=attempt?.normalization_error;
  const validation=run.error==='INVALID_STRUCTURED_OUTPUT'&&!issue?validationFailure(attempt):null;
  box.append(element('p',issue?normalizationReasons[issue.category]||normalizationReasons.other_normalization_error:validation?.message||failureReasons[run.error]||'Analysis could not complete. Review the inputs and Provider Settings, then retry.','ai-failure-help'));
  const location=issue?locationLabel(issue.location):validation?.location;if(location)box.append(element('p',location));
  if(validation?.more)box.append(element('p','Other response fields also need review. Correcting this item may not resolve the whole response.'));
}
