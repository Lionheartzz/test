const icons={
  home:'m3 11 9-8 9 8M5 10v11h5v-7h4v7h5V10',
  projects:'M3 5h7l2 3h9v13H3V5zM3 10h18',
  block:'m12 3 9 5v10l-9 5-9-5V8l9-5Zm0 10 9-5M12 13 3 8m9 5v10',
  new:'M12 4v16M4 12h16',
  ai:'M4 5h6v6H4zM14 16h6v6h-6zM7 11v8h7M10 8h7v8M17 2v7m-3-3h6',
  library:'M3 4h5v17H3zM10 4h5v17h-5zM17 4l4-1 4 17-4 1z',
  schematic:'M3 7h6v6H3zM15 7h6v6h-6zM9 10h6M6 13v7h12v-7',
  import:'M5 3h9l5 5v5M14 3v6h5M5 3v19h14v-4M9 15h12m-3-3 3 3-3 3',
  arrow:'M4 12h16m-6-6 6 6-6 6',
};
export function homeIcon(kind){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 26 26');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[kind]||icons.block);svg.append(path);return svg;
}

export function renderHome({element,action,api,launch,hasProject,returnToDraft,startSetup,navigate}){
  const header=element('header',null,'home-header'),brand=element('div',null,'home-brand');
  brand.append(homeIcon('block'),element('strong','PMC'),element('span','MANIFOLD STUDIO'));
  const statuses=element('div',null,'home-services'),service=element('span','Checking service…'),database=element('span','Checking library…');
  statuses.setAttribute('role','status');statuses.append(service,database);header.append(brand,statuses);
  const layout=element('div',null,'home-layout'),sidebar=element('nav',null,'home-sidebar'),content=element('div',null,'home-content');sidebar.setAttribute('aria-label','Home navigation');
  const navigationButtons={},pages=new Map(),scroll=new Map();let current='home';
  for(const [section,entries]of [
    ['WORKSPACE',[
      ['home','Home','home'],['projects','Projects','projects'],['new','New Manifold','new'],['ai','AI Design','ai'],
    ]],
    ['LIBRARY',[
      ['library','Engineering Library','library'],
    ]],
  ]){
    sidebar.append(element('span',section,'home-nav-heading'));
    for(const [icon,label,module]of entries){
      const button=action(sidebar,'',()=>navigate(module));
      button.append(homeIcon(icon),element('span',label));button.setAttribute('aria-label',label);button.title=label;
      navigationButtons[module]=button;
      if(icon==='home')button.setAttribute('aria-current','page');
    }
  }
  const sidebarNote=element('p',null,'home-sidebar-note');sidebar.append(sidebarNote);
  const sidebarFoot=element('div',null,'home-sidebar-foot');sidebarFoot.append(element('span','LOCAL WORKSPACE'),element('small','Projects and drawings stay in this workspace.'));sidebar.append(sidebarFoot);
  layout.append(sidebar,content);
  const titlebar=element('div',null,'home-titlebar'),title=element('h1','Start a manifold');title.id='home-start';title.tabIndex=-1;titlebar.append(title);
  const titleActions=element('div',null,'home-title-actions');
  const returnButton=action(titleActions,'Return to current draft',returnToDraft);returnButton.classList.add('home-return');
  titlebar.append(titleActions);content.append(titlebar);
  const start=element('section',null,'home-module');start.dataset.module='home';pages.set('home',start);content.append(start);
  const cards=element('div',null,'home-start-cards');start.append(cards);
  const quick=element('section',null,'home-card home-quick'),quickHead=element('div',null,'home-card-heading');
  const quickTitle=element('h2','Quick block setup');quickHead.append(homeIcon('block'),quickTitle);
  const units=element('select');units.setAttribute('aria-label','Unit context');for(const [value,text]of [['metric','Metric · mm'],['inch','Inch · in']]){const option=element('option',text);option.value=value;units.append(option);}quickHead.append(units);quick.append(quickHead);cards.append(quick);
  const form=element('form',null,'home-setup-form');quick.append(form);const first=element('div',null,'home-setup-first');form.append(first);
  function field(parent,label,control){const wrap=element('label',null,'home-field');wrap.append(element('span',label),control);parent.append(wrap);return control;}
  const name=field(first,'Project name',element('input'));name.value='New manifold';name.required=true;name.maxLength=120;
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
  form.onsubmit=event=>{event.preventDefault();if(!name.value.trim()){name.setCustomValidity('Enter a project name.');name.reportValidity();return;}const selected=material.selectedOptions[0];startSetup({name:name.value.trim(),unit:units.value,dimensions:inputs.map(input=>input.valueAsNumber),material:selected?.value?{id:selected.value,name:selected.dataset.name}:null},continueButton);};name.oninput=()=>name.setCustomValidity('');
  api('/api/materials').then(result=>{
    if(!material.isConnected)return;
    for(const row of result.items||[]){if(!row.active||row.selectable===false)continue;const option=element('option',row.display_name);option.value=row.id;option.dataset.name=row.display_name;material.append(option);}
    material.disabled=false;material.dataset.loaded='true';
  }).catch(()=>{if(material.isConnected){placeholder.textContent='Material list unavailable · choose in setup';material.title='Could not load /api/materials. Continue to choose a material in engineering setup.';}});
  const ai=element('section',null,'home-card home-ai'),aiHead=element('div',null,'home-card-heading');aiHead.append(homeIcon('ai'),element('h2','AI from schematic'),element('span','PDF / PNG / JPEG','home-file-types'));ai.append(aiHead);
  const aiBody=element('div',null,'home-ai-body'),diagram=element('div',null,'home-schematic-icon');diagram.append(homeIcon('schematic'));
  const aiCopy=element('div');aiCopy.append(element('h3','Start with your hydraulic circuit'),element('p','Use your configured AI provider to interpret a schematic and prepare an editable manifold draft.'));aiBody.append(diagram,aiCopy);ai.append(aiBody);
  const aiFoot=element('div',null,'home-ai-footer');aiFoot.append(element('small','Selected documents are sent to your provider.'));
  const aiButton=action(aiFoot,'Open AI Design',()=>navigate('ai'));aiButton.append(homeIcon('arrow'));ai.append(aiFoot);cards.append(ai);
  const projects=element('section',null,'home-projects');projects.id='home-projects';projects.setAttribute('aria-label','Recent projects');start.append(projects);
  function page(module){if(!pages.has(module)){const pane=element('section',null,'home-module');pane.dataset.module=module;pane.hidden=true;pages.set(module,pane);content.append(pane);}return pages.get(module);}
  function updateDraft(){returnButton.hidden=!hasProject();sidebarNote.textContent=hasProject()?'Current draft stays open while you browse Home.':'Select a saved project from a management page, or create a new manifold.';}
  function select(module,label){
    scroll.set(current,content.scrollTop);const pane=page(module);current=module;
    for(const [key,node]of pages)node.hidden=key!==module;
    for(const [key,button]of Object.entries(navigationButtons)){button.removeAttribute('aria-current');if(key===module)button.setAttribute('aria-current','page');}
    if(module==='home')start.append(projects);else if(module==='projects')pane.append(projects);
    title.textContent=label;updateDraft();content.scrollTop=scroll.get(module)||0;title.focus({preventScroll:true});return pane;
  }
  function setTitle(label){title.textContent=label;}
  updateDraft();
  Promise.allSettled([api('/api/health'),api('/api/catalog/manifest')]).then(([health,manifest])=>{
    if(!header.isConnected)return;
    const online=health.status==='fulfilled'&&health.value.service==='pmc-manifold';
    service.textContent=online?(health.value.network?.mode==='lan'?'LAN':'LOCAL'):'SERVICE UNAVAILABLE';service.dataset.state=online?'ready':'error';
    const ready=manifest.status==='fulfilled'&&Number.isFinite(manifest.value.schema_version);
    database.textContent=ready?'LIBRARY READY':'LIBRARY UNAVAILABLE';database.dataset.state=ready?'ready':'error';
    database.title=ready?'Engineering Library available':'Engineering Library could not be checked. Reload the page to retry.';
  });
  return {header,layout,projects,content,page,select,setTitle,updateDraft};
}
