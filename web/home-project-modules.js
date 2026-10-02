// Saved-project indexes only. Opening a tool always names a selected project.
export const projectModules={
  model:{title:'Model Management',action:'Open Model',columns:['Project','Block / mm','Features','Engineering','Modified','Actions']},
  drawing:{title:'Drawing Management',action:'Open Drawing',columns:['Project','Engineering freshness','Modified','Actions']},
  nets:{title:'Hydraulic Nets Management',action:'Open Nets',columns:['Project','Nets','Engineering','Modified','Actions']},
  schematic:{title:'Schematic Management',action:'Open Schematic',columns:['Project','Schematic documents','Modified','Actions']},
  review:{title:'Engineering Review',action:'Open Review',columns:['Project','Engineering','Last build checks','Modified','Actions']},
};

export function projectManagement({element,action,loadRows,onOpen},parent,module){
  const config=projectModules[module];let rows=[],query='',archived=false,page=0,request=0;
  parent.append(element('p','Select a saved project to open its '+({model:'Model',drawing:'Drawing workspace',nets:'Hydraulic Nets',schematic:'Schematic',review:'Engineering Review'})[module]+'.','home-module-intro'));
  const filters=element('div',null,'home-project-filters'),search=element('input');search.type='search';search.placeholder='Search projects…';search.setAttribute('aria-label','Search '+config.title);filters.append(search);
  const archive=action(filters,'Show archived projects',()=>{archived=!archived;page=0;paint();});parent.append(filters);
  const frame=element('div',null,'home-table-frame'),table=element('table',null,'home-project-table home-management-table'),head=element('thead'),header=element('tr'),body=element('tbody');
  table.setAttribute('aria-label',config.title);for(const label of config.columns){const cell=element('th',label);cell.scope='col';header.append(cell);}head.append(header);table.append(head,body);frame.append(table);parent.append(frame);
  const footer=element('div',null,'home-table-footer'),count=element('span'),paging=element('div');count.setAttribute('role','status');footer.append(count,paging);parent.append(footer);
  const modified=row=>row.updated_at?new Date(row.updated_at).toLocaleString():'—';
  const status=row=>row.error?'UNREADABLE':(row.status||'Not recorded')+(row.status==='SAVED DRAFT'?' · Not validated':row.stale===true?' · Stale':row.stale===false?' · Current':'');
  function paint(){
    archive.textContent=archived?'Show active projects':'Show archived projects';archive.setAttribute('aria-pressed',String(archived));body.replaceChildren();paging.replaceChildren();
    const filtered=rows.filter(row=>!!row.archived===archived&&row.name.toLowerCase().includes(query.toLowerCase()));
    page=Math.max(0,Math.min(page,Math.ceil(filtered.length/10)-1));
    for(const row of filtered.slice(page*10,page*10+10)){
      const tr=element('tr');tr.dataset.projectId=row.id;const values=[row.name];
      if(module==='model')values.push(row.block&&['length','width','height'].every(key=>Number.isFinite(row.block[key]))?['length','width','height'].map(key=>Number(row.block[key].toFixed(2))).join(' × '):'—',row.features??'—',status(row));
      if(module==='drawing')values.push(status(row));
      if(module==='nets')values.push(row.net_count??'—',status(row));
      if(module==='schematic')values.push(row.schematic_count??'—');
      if(module==='review'){const checks=row.engineering_counts;values.push(status(row),checks?`${checks.PASS??'—'} PASS · ${checks.WARNING??'—'} WARNING · ${checks.FAIL??'—'} FAIL`:'No retained build counts');}
      values.push(modified(row));for(const value of values)tr.append(element('td',String(value)));
      const buttons=element('td',null,'home-row-actions');if(!row.error){const button=action(buttons,config.action,()=>onOpen(row,module,button));button.setAttribute('aria-label',config.action+' · '+row.name);}tr.append(buttons);body.append(tr);
    }
    if(!filtered.length){const tr=element('tr'),cell=element('td',query?'No matching projects.':archived?'No archived projects.':'No saved projects yet. Create or import a manifold.','home-empty');cell.colSpan=config.columns.length;tr.append(cell);body.append(tr);}
    count.textContent=filtered.length?`${page*10+1}–${Math.min(page*10+10,filtered.length)} of ${filtered.length} projects`:'0 projects';
    if(filtered.length>10){action(paging,'Previous',()=>{page--;paint();}).disabled=page===0;action(paging,'Next',()=>{page++;paint();}).disabled=page*10+10>=filtered.length;}
  }
  search.oninput=()=>{query=search.value;page=0;paint();};
  async function refresh(){const ticket=++request;table.setAttribute('aria-busy','true');count.textContent='Loading saved projects…';try{const next=await loadRows();if(ticket!==request||!parent.isConnected)return;rows=next;paint();}catch(error){if(ticket!==request)return;body.replaceChildren();const tr=element('tr'),cell=element('td',null,'home-empty error');cell.colSpan=config.columns.length;cell.append(element('span','Could not load projects. '+error.message));action(cell,'Retry',refresh);tr.append(cell);body.append(tr);count.textContent='Project list unavailable';}finally{if(ticket===request)table.setAttribute('aria-busy','false');}}
  return {refresh};
}
