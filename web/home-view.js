const icons={
  home:'m3 11 9-8 9 8M5 10v11h5v-7h4v7h5V10',
  block:'m12 3 9 5v10l-9 5-9-5V8l9-5Zm0 10 9-5M12 13 3 8m9 5v10',
  new:'M12 4v16M4 12h16',
  drawing:'M4 3h16v19H4zM7 7h6v7H7zM7 18h10m-2-11h2m-2 4h2',
  ai:'M4 5h6v6H4zM14 16h6v6h-6zM7 11v8h7M10 8h7v8M17 2v7m-3-3h6',
  nets:'M4 5h5v5H4zM15 15h5v5h-5zM9 7h9v8M6 10v8h9',
  library:'M3 4h5v17H3zM10 4h5v17h-5zM17 4l4-1 4 17-4 1z',
  schematic:'M3 7h6v6H3zM15 7h6v6h-6zM9 10h6M6 13v7h12v-7',
  review:'M8 4H4v18h16V4h-4M8 2h8v5H8zM8 13l2 2 5-5m-7 9h8',
  search:'M16 16l6 6M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  import:'M5 3h9l5 5v5M14 3v6h5M5 3v19h14v-4M9 15h12m-3-3 3 3-3 3',
  arrow:'M4 12h16m-6-6 6 6-6 6',
};
export function homeIcon(kind){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 26 26');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[kind]||icons.block);svg.append(path);return svg;
}

export function renderHome({element,action,api,launch,hasProject,returnToDraft,startSetup}){
  const header=element('header',null,'home-header'),brand=element('div',null,'home-brand');
  brand.append(homeIcon('block'),element('strong','PMC'),element('span','MANIFOLD STUDIO'));
  const statuses=element('div',null,'home-services'),service=element('span','Checking service…'),database=element('span','Checking engineering DB…');
  statuses.setAttribute('role','status');statuses.append(service,database);header.append(brand,statuses);
  const layout=element('div',null,'home-layout'),sidebar=element('nav',null,'home-sidebar');sidebar.setAttribute('aria-label','Home navigation');
  const jump=id=>{const target=layout.querySelector('#'+id);target?.scrollIntoView({block:'nearest'});target?.focus({preventScroll:true});};
  for(const [section,entries]of [
    ['WORKSPACE',[
      ['home','Home',()=>jump('home-start'),false],
      ['new','New Manifold','project-new',false],
      ['block','Model',()=>hasProject()?returnToDraft():launch('project-new'),false],
      ['drawing','Drawing','drawings-open',true],
      ['ai','AI Design','ai-design-open',false],
    ]],
    ['ENGINEERING',[
      ['nets','Hydraulic Nets','nets-open',true],
      ['library','Engineering Library','library-open',false],
      ['schematic','Schematic','schematic-open',true],
      ['review','Engineering Review','review-open',true],
    ]],
  ]){
    sidebar.append(element('span',section,'home-nav-heading'));
    for(const [icon,label,handler,needsProject]of entries){
      const button=action(sidebar,'',()=>typeof handler==='function'?handler():launch(handler,button));
      button.append(homeIcon(icon),element('span',label));button.setAttribute('aria-label',label);button.title=label;
      if(icon==='home')button.setAttribute('aria-current','page');
      if(needsProject&&!hasProject()){button.disabled=true;button.title=label+' · Open or create a manifold first';}
    }
  }
  const sidebarNote=element('p',hasProject()?'Current draft stays open while you browse Home.':'Open or create a manifold to use project engineering tools.','home-sidebar-note');sidebar.append(sidebarNote);
  const sidebarFoot=element('div',null,'home-sidebar-foot');sidebarFoot.append(element('span','LOCAL WORKSPACE'),element('small','Projects and drawings stay in this workspace.'));sidebar.append(sidebarFoot);
  const content=element('div',null,'home-content');layout.append(sidebar,content);
  const titlebar=element('div',null,'home-titlebar'),title=element('h1','Start a manifold');title.id='home-start';title.tabIndex=-1;titlebar.append(title);
  const titleActions=element('div',null,'home-title-actions');
  const importButton=action(titleActions,'Import Project',()=>launch('project-import',importButton));importButton.prepend(homeIcon('import'));
  if(hasProject())action(titleActions,'Return to current draft',returnToDraft).classList.add('home-return');
  titlebar.append(titleActions);content.append(titlebar);
  const cards=element('div',null,'home-start-cards');content.append(cards);
  const quick=element('section',null,'home-card home-quick'),quickHead=element('div',null,'home-card-heading');
  const quickTitle=element('h2','Quick block setup');quickHead.append(homeIcon('block'),quickTitle);
  const units=element('select');units.setAttribute('aria-label','Unit context');for(const [value,text]of [['metric','Metric · mm'],['inch','Inch · in']]){const option=element('option',text);option.value=value;units.append(option);}quickHead.append(units);quick.append(quickHead);cards.append(quick);
  const form=element('form',null,'home-setup-form');quick.append(form);const first=element('div',null,'home-setup-first');form.append(first);
  function field(parent,label,control){const wrap=element('label',null,'home-field');wrap.append(element('span',label),control);parent.append(wrap);return control;}
  const name=field(first,'Project name',element('input'));name.value='New manifold';name.required=true;name.maxLength=160;
  const material=field(first,'Material',element('select'));material.setAttribute('aria-label','Material');const placeholder=element('option','Choose in engineering setup');placeholder.value='';material.append(placeholder);material.disabled=true;
  const dimensions=element('div',null,'home-envelope');form.append(dimensions);const mm=[160,100,100],inputs=[],labels=[];
  for(const [index,label]of ['Length','Width','Height'].entries()){
    const input=element('input');input.type='number';input.step='any';input.required=true;input.min='0.001';input.max='2000';input.value=mm[index];
    field(dimensions,label+' / mm',input);inputs.push(input);labels.push(input.parentElement.firstElementChild);
    input.oninput=()=>{mm[index]=input.valueAsNumber*(units.value==='inch'?25.4:1);};
  }
  units.onchange=()=>inputs.forEach((input,index)=>{input.value=mm[index]/(units.value==='inch'?25.4:1);input.max=2000/(units.value==='inch'?25.4:1);labels[index].textContent=['Length','Width','Height'][index]+' / '+(units.value==='inch'?'in':'mm');});
  const setupFooter=element('div',null,'home-setup-footer'),setupNote=element('span','Next: nets, ports, cavities & review.');setupFooter.append(setupNote);
  const continueButton=element('button','Continue Engineering Setup','primary');continueButton.type='submit';continueButton.append(homeIcon('arrow'));setupFooter.append(continueButton);form.append(setupFooter);
  form.onsubmit=event=>{event.preventDefault();if(!name.value.trim()){name.setCustomValidity('Enter a project name.');name.reportValidity();return;}startSetup({name:name.value.trim(),unit:units.value,dimensions:inputs.map(input=>input.valueAsNumber),material:material.selectedOptions[0]?.dataset.name||''},continueButton);};name.oninput=()=>name.setCustomValidity('');
  api('/api/materials').then(result=>{
    if(!material.isConnected)return;
    for(const row of result.items||[]){if(!row.active)continue;const option=element('option',row.display_name);option.value=row.id;option.dataset.name=row.display_name;material.append(option);}
    material.disabled=false;material.dataset.loaded='true';
  }).catch(()=>{if(material.isConnected){placeholder.textContent='Material list unavailable · choose in setup';material.title='Could not load /api/materials. Continue to choose a material in engineering setup.';}});
  const ai=element('section',null,'home-card home-ai'),aiHead=element('div',null,'home-card-heading');aiHead.append(homeIcon('ai'),element('h2','AI from schematic'),element('span','PDF / PNG / JPEG','home-file-types'));ai.append(aiHead);
  const aiBody=element('div',null,'home-ai-body'),diagram=element('div',null,'home-schematic-icon');diagram.append(homeIcon('schematic'));
  const aiCopy=element('div');aiCopy.append(element('h3','Start with your hydraulic circuit'),element('p','Use your configured AI provider to interpret a schematic and prepare an editable manifold draft.'));aiBody.append(diagram,aiCopy);ai.append(aiBody);
  const aiFoot=element('div',null,'home-ai-footer');aiFoot.append(element('small','Selected documents are sent to your provider.'));
  const aiButton=action(aiFoot,'Open AI Design',()=>launch('ai-design-open',aiButton));aiButton.append(homeIcon('arrow'));ai.append(aiFoot);cards.append(ai);
  const projects=element('section',null,'home-projects');projects.setAttribute('aria-label','Recent projects');content.append(projects);
  const library=element('section',null,'home-library-search');library.setAttribute('aria-label','Engineering Library quick search');content.append(library);
  Promise.allSettled([api('/api/health'),api('/api/catalog/manifest')]).then(([health,manifest])=>{
    if(!header.isConnected)return;
    const online=health.status==='fulfilled'&&health.value.service==='pmc-manifold';
    service.textContent=online?(health.value.network?.mode==='lan'?'LAN':'LOCAL'):'SERVICE UNAVAILABLE';service.dataset.state=online?'ready':'error';
    const ready=manifest.status==='fulfilled'&&Number.isFinite(manifest.value.schema_version);
    database.textContent=ready?'ENGINEERING DB READY':'ENGINEERING DB UNAVAILABLE';database.dataset.state=ready?'ready':'error';
    database.title=ready?'SQLite schema '+manifest.value.schema_version:'Engineering database could not be checked. Reload the page to retry.';
  });
  return {header,layout,projects,library};
}

export function renderLibrarySearch(parent,{element,action,api,launch}){
  const heading=element('div',null,'home-library-heading');heading.append(homeIcon('library'),element('h2','Engineering Library'),element('span','Cavities · Cartridges · Threads'));
  const open=action(heading,'Open Engineering Library',()=>launch('library-open',open));parent.append(heading);
  const label=element('label',null,'home-library-input');label.append(homeIcon('search'));const search=element('input');search.type='search';search.placeholder='Search cavity, cartridge, thread…';search.setAttribute('aria-label','Search engineering library');label.append(search);parent.append(label);
  const results=element('div',null,'home-library-results');results.setAttribute('aria-live','polite');parent.append(results);
  let timer,request=0;
  search.oninput=()=>{
    clearTimeout(timer);const token=++request,q=search.value.trim();results.replaceChildren();if(!q)return;
    results.append(element('p','Searching engineering records…','home-search-message'));
    timer=setTimeout(async()=>{
      const definitions=[['Cavity','/api/catalog',row=>row.name,row=>row.thread_spec||row.family],['Cartridge','/api/cartridges',row=>[row.manufacturer,row.model].filter(Boolean).join(' '),row=>row.function],['Thread','/api/threads',row=>row.display_name,row=>row.normalized_family||row.family]];
      const response=await Promise.allSettled(definitions.map(([,path])=>api(path+'?'+new URLSearchParams({q,limit:6}))));
      if(token!==request||!results.isConnected)return;results.replaceChildren();
      const groups=response.map((result,index)=>result.status==='fulfilled'?(result.value.items||[]).map(row=>({row,type:definitions[index][0],name:definitions[index][2](row),detail:definitions[index][3](row)})):[]);
      const found=[];for(let i=0;i<6;i++)for(const group of groups)if(group[i]&&found.length<6)found.push(group[i]);
      for(const item of found){const row=element('div',null,'home-library-result');row.append(element('span',item.type,'home-result-type'),element('strong',item.name),element('span',item.detail||'','home-result-detail'));row.title=item.row.id;
        if(item.row.usable===0||item.row.usable===false){const unavailable=element('span','Unavailable','home-result-unavailable');unavailable.title=item.row.unusable_reason||'This definition is unavailable for placement.';row.append(unavailable);}results.append(row);}
      const failed=response.flatMap((result,index)=>result.status==='rejected'?[definitions[index][0]]:[]);
      if(failed.length)results.append(element('p',failed.join(', ')+' search unavailable. Edit the search to retry.','home-search-message error'));
      if(!found.length&&!failed.length)results.append(element('p','No matching engineering records. Try another designation or name.','home-search-message'));
    },220);
  };
}
