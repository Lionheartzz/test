export function analysisStatus(row,job){
  if(job?.operation==='analyze'&&job.task_id===row.id&&['queued','running'].includes(job.status))return 'Running';
  const last=row.latest_attempt||row.latest_run;
  if(last?.status==='failed')return 'Failed'+(last.error?' · '+last.error:'');
  if(row.stale)return 'Inputs changed · re-analysis required';
  return !last?'Not analyzed':last.status==='completed'?'Completed':last.status==='running'?'Running':'Not analyzed';
}

export function documentSummary(row){
  const names=row.document_names||[];
  return !row.documents?'No schematic documents':row.documents===1?names[0]||'1 document':`${row.documents} documents · ${names[0]||'schematic'} +${row.documents-1}`;
}
