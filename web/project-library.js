import {renderHome,homeIcon} from './home-view.js';
import {engineeringName} from './engineering-labels.js';
import {libraryUI} from './library-ui.js';

export function prefillGuidedBlock($,values){
  const input=label=>[...$('workflow-content').querySelectorAll('input,select')].find(node=>node.getAttribute('aria-label')===label);
  const set=(label,value)=>{const node=input(label);if(!node)throw Error('Engineering setup field is unavailable: '+label);node.value=value;node.dispatchEvent(new Event('change',{bubbles:true}));};
  set('Project context',values.unit);set('Project name',values.name);
  if(values.material){
    const node=input('Material');if(!node)throw Error('Engineering setup field is unavailable: Material');
    node.dataset.prefillMaterialId=values.material.id;
    set('Material',values.material.id);
  }
  const suffix=values.unit==='inch'?'in':'mm';['Length','Width','Height'].forEach((label,index)=>set(label+' / '+suffix,values.dimensions[index]));
}

export function projectLibrary(ctx){
  const {$,element,action,api,post,openProject,isDirty,hasProject,onDeleted}=ctx;
  const home=$('project-home');let query='',archived=false,page=0,generation=0,view=null,projectList=null,selected='home',opening=false;
  let cachedRows=null,rowsRequest=null,rowsGeneration=0,inlineLibrary=null;
  function loadRows(force=false){
    if(force){cachedRows=null;rowsRequest=null;rowsGeneration++;}
    if(cachedRows)return Promise.resolve(cachedRows);if(rowsRequest)return rowsRequest;
    const ticket=rowsGeneration;
    rowsRequest=api('/api/projects').then(rows=>{if(ticket===rowsGeneration)cachedRows=rows;return rows;}).finally(()=>{if(ticket===rowsGeneration)rowsRequest=null;});return rowsRequest;
  }
  async function refreshProjects(){await loadRows(true);view?.updateDraft();await projectList?.refresh();}
  const returnToDraft=()=>{++generation;document.body.classList.remove('home');$('select-block').focus({preventScroll:true});};
  function launch(id,trigger=document.activeElement){
    const command=$(id);if(command.disabled)return false;
    if(id==='drawings-open')returnToDraft();
    command.click();const dialog=document.querySelector('dialog[open]');
    dialog?.addEventListener('close',()=>{if(trigger?.isConnected&&trigger.getClientRects().length)trigger.focus();},{once:true});
    return !!dialog;
  }
  function startSetup(values,trigger){
    if(!launch('project-new',trigger))return;
    // Prefill existing, labelled step-one controls through their normal change
    // handlers. The existing five-step workflow remains the only draft creator.
    try{prefillGuidedBlock($,values);}catch(error){$('workflow-error').textContent=error.message+' Please complete step 1 directly.';}
  }
  async function open(row){
    if(opening)return;
    if(isDirty()&&!confirm('Discard the current unsaved draft and open this project?'))return;
    const ticket=generation;opening=true;
    try{await openProject(row.id,()=>ticket===generation&&document.body.classList.contains('home'));}
    catch(error){alert(error.message);}finally{opening=false;}
  }
  function drawings(row){
    if(isDirty()&&!confirm('Leave the unsaved manifold draft and open project drawings?'))return;
    location.href='/drawing.html?project='+encodeURIComponent(row.id);
  }
  async function manage(row,op){
    let name;
    if(['rename','duplicate'].includes(op)){name=prompt('Project name',op==='duplicate'?row.name+' copy':row.name);if(!name?.trim())return;name=name.trim();}
    try{await post(`/api/projects/${row.id}/manage`,{expected_revision:row.revision,action:op,name:name||null});await refreshProjects();}catch(error){alert(error.message);}
  }
  async function remove(row){
    const name=prompt(`Permanently delete “${row.name}” with its drawings and revision history? This cannot be undone. Shared PMC/MDTools records, assets and retained build history are retained. Type the exact project name to confirm.`);
    if(name===null)return;if(name!==row.name){alert('Project name did not match. Nothing was deleted.');return;}
    try{await post(`/api/projects/${row.id}/delete`,{expected_revision:row.revision,confirm_name:name});onDeleted(row.id);await refreshProjects();}catch(error){alert(error.message);}
  }
  function projectTable(parent){
    const heading=element('div',null,'home-project-heading'),title=element('h2',archived?'Archived projects':'Recent projects');heading.append(title);
    const filters=element('div',null,'home-project-filters'),search=element('input');search.type='search';search.placeholder='Search projects…';search.setAttribute('aria-label','Search saved projects');search.value=query;filters.append(search);
    const archive=action(filters,archived?'Show active projects':'Show archived projects',()=>{archived=!archived;page=0;paint();});archive.setAttribute('aria-pressed',String(archived));heading.append(filters);parent.append(heading);
    const frame=element('div',null,'home-table-frame'),table=element('table',null,'home-project-table');table.setAttribute('aria-label','Saved manifold projects');
    const head=element('thead'),headRow=element('tr');for(const text of ['Project','Block / mm','Features','Engineering','Modified','Actions']){const th=element('th',text);th.scope='col';headRow.append(th);}head.append(headRow);table.append(head);const body=element('tbody');table.append(body);frame.append(table);parent.append(frame);
    const footer=element('div',null,'home-table-footer'),count=element('span'),paging=element('div');count.setAttribute('role','status');footer.append(count,paging);parent.append(footer);
    const menu=element('div',null,'home-project-menu');menu.id='home-project-menu';menu.setAttribute('popover','auto');menu.setAttribute('role','menu');parent.append(menu);
    let moreTrigger=null;
    menu.addEventListener('toggle',()=>{moreTrigger?.setAttribute('aria-expanded',String(menu.matches(':popover-open')));});
    menu.addEventListener('keydown',event=>{
      const items=[...menu.querySelectorAll('button')],index=items.indexOf(document.activeElement);
      if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();items[event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length]?.focus();}
    });
    function more(row,button){
      if(menu.matches(':popover-open')){menu.hidePopover();if(moreTrigger===button)return;}
      moreTrigger=button;menu.replaceChildren();
      for(const [label,op]of [['Rename','rename'],['Duplicate','duplicate'],[row.archived?'Restore':'Archive',row.archived?'restore':'archive'],['Delete permanently','delete']]){
        const item=action(menu,label,()=>{menu.hidePopover();button.focus();op==='delete'?remove(row):manage(row,op);});item.setAttribute('role','menuitem');if(op==='delete')item.classList.add('home-delete');
      }
      const rect=button.getBoundingClientRect();menu.style.left=Math.max(8,Math.min(rect.right-180,innerWidth-188))+'px';menu.style.top=Math.max(8,Math.min(rect.bottom+4,innerHeight-174))+'px';menu.showPopover();menu.querySelector('button')?.focus();
    }
    let rows=[];
    function paint(){
      title.textContent=archived?'Archived projects':'Recent projects';archive.textContent=archived?'Show active projects':'Show archived projects';archive.setAttribute('aria-pressed',String(archived));
      if(menu.matches(':popover-open'))menu.hidePopover();body.replaceChildren();paging.replaceChildren();
      const visible=rows.filter(row=>!!row.archived===archived&&row.name.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>(Date.parse(b.updated_at)||0)-(Date.parse(a.updated_at)||0));
      const size=5;page=Math.max(0,Math.min(page,Math.ceil(visible.length/size)-1));
      for(const row of visible.slice(page*size,(page+1)*size)){
        const tr=element('tr');tr.dataset.projectId=row.id;
        const project=element('td',null,'home-project-name'),name=element('span',row.error?engineeringName(row.name,'Unreadable project'):row.name);name.title=name.textContent;project.append(homeIcon('block'),name);tr.append(project);
        const dimensions=row.block&&['length','width','height'].every(key=>Number.isFinite(row.block[key]))?['length','width','height'].map(key=>Number(row.block[key].toFixed(2))).join(' × '):'—';
        const block=element('td',dimensions,'home-block-size');block.title='Stored dimensions in mm'+(row.project_context?' · '+row.project_context+' project context':'');tr.append(block,element('td',row.features??'—','home-feature-count'));
        const state=element('td'),badge=element('span',row.error?'UNREADABLE':row.status,'home-project-status');badge.dataset.state=row.error?'unreadable':String(row.status).toLowerCase().replaceAll(' ','-');badge.title=row.error||row.status;state.append(badge);tr.append(state);
        const modified=element('td',row.updated_at?new Date(row.updated_at).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'—','home-project-date');modified.title=row.updated_at?new Date(row.updated_at).toLocaleString():row.error||'';tr.append(modified);
        const actions=element('td',null,'home-row-actions');tr.append(actions);body.append(tr);
        if(!row.error){action(actions,'Open CAD',()=>open(row));action(actions,'Drawing',()=>drawings(row));const button=action(actions,'More',()=>more(row,button));button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-controls',menu.id);button.setAttribute('aria-expanded','false');button.title='Manage '+row.name;}
      }
      if(!visible.length){const tr=element('tr'),cell=element('td',query?'No matching projects. Try another name.':archived?'No archived projects.':'No saved projects yet. Start with Quick block setup or import a project.','home-empty');cell.colSpan=6;tr.append(cell);body.append(tr);}
      count.textContent=visible.length?`${page*size+1}–${Math.min((page+1)*size,visible.length)} of ${visible.length} ${archived?'archived':'active'} projects`:'0 projects';
      if(visible.length>size){action(paging,'Previous',()=>{page--;paint();}).disabled=page===0;action(paging,'Next',()=>{page++;paint();}).disabled=(page+1)*size>=visible.length;}
    }
    search.oninput=()=>{query=search.value;page=0;paint();};
    let request=0;
    async function load(){
      const ticket=++request;
      body.replaceChildren();table.setAttribute('aria-busy','true');count.textContent='Loading saved projects…';
      try{const result=await loadRows();if(ticket!==request||!body.isConnected)return;rows=result;paint();}
      catch(error){if(ticket!==request||!body.isConnected)return;const tr=element('tr'),cell=element('td',null,'home-empty error');cell.colSpan=6;cell.append(element('span','Could not load saved projects. '+error.message));action(cell,'Retry loading projects',load);tr.append(cell);body.replaceChildren(tr);count.textContent='Project list unavailable';}
      finally{if(ticket===request)table.setAttribute('aria-busy','false');}
    }
    load();return {refresh:load,hideMenu:()=>{if(menu.matches(':popover-open'))menu.hidePopover();}};
  }
  async function show(module='home'){
    if(!['home','projects','new','ai','library'].includes(module))throw Error('This page is not available. Open project tools from Projects.');
    ++generation;selected=module;document.body.classList.add('home');home.setAttribute('aria-label','Engineering Home');
    if(!view){view=renderHome({element,action,api,launch,hasProject,returnToDraft,startSetup,navigate:id=>show(id).catch(error=>alert(error.message))});home.append(view.header,view.layout);projectList=projectTable(view.projects);}
    projectList.hideMenu();
    const titles={home:'Start a manifold',projects:'Projects',new:'New Manifold',ai:'AI Design Management',library:'Engineering Library'};
    const pane=view.select(module,titles[module]);
    if(module==='projects'&&!pane.querySelector('.home-project-actions')){const actions=element('div',null,'home-project-actions action-row');const button=action(actions,'Import Project',()=>launch('project-import',button));button.prepend(homeIcon('import'));pane.prepend(actions);}
    if(module==='home'||module==='projects'){await projectList.refresh();return;}
    if(module==='new'&&!pane.childElementCount){pane.append(element('p','Create a new manifold through the existing five-step engineering setup.','home-module-intro'));const button=action(pane,'Start Guided manifold setup',()=>launch('project-new',button));button.classList.add('primary');return;}
    if(module==='ai')return ctx.ai.mountManagement(pane,{isCurrent:()=>selected==='ai'&&document.body.classList.contains('home')});
    if(module==='library'&&!inlineLibrary){const error=element('p',null,'error'),body=element('div');error.setAttribute('role','alert');pane.append(body,error);const inlineContext={...ctx,get:()=>null,currentDefinitions:()=>ctx.get()?.features||[],$:id=>id==='workflow-content'?body:id==='workflow-error'?error:$(id)};
      inlineLibrary=libraryUI(inlineContext,{open:title=>{body.replaceChildren();error.textContent='';if(selected==='library')view.setTitle(title);},insert:()=>{},scrollContainer:()=>view.content});inlineLibrary();}
    else if(module==='library')view.setTitle(inlineLibrary.currentTitle||'Engineering Library');
  }
  ctx.ai.setManagementNavigation(()=>{if($('workflow-dialog').open)$('workflow-dialog').close();return show('ai');});
  $('ai-design-open').onclick=()=>show('ai').catch(error=>alert(error.message));
  $('projects-open').onclick=()=>{loadRows(true).catch(()=>{});return show('home');};
  return {show};
}
