async page => {
  const base='__BASE_URL__',output='__OUTPUT_DIR__',headers={'X-PMC-Request':'local-console'},errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const assert=(v,m)=>{if(!v)throw Error(m);},json=async r=>{assert(r.ok(),await r.text());return r.json();};
  const api=p=>page.request.get(base+p).then(json),dialog=page.locator('#workflow-dialog');
  const close=async()=>{await dialog.press('Escape');await dialog.waitFor({state:'hidden'});};
  const settings=async()=>{await page.getByRole('button',{name:'Project actions',exact:true}).click();await page.locator('#project-settings').click();await dialog.getByRole('heading',{name:'Project Settings',exact:true}).waitFor();};
  const nets=async()=>{await page.getByRole('button',{name:/^Engineering(?: \d+)?$/}).click();await page.locator('#nets-open').click();await dialog.getByText(/Effective pressure:/).first().waitFor();};
  const edit=async(label,value)=>{await dialog.getByLabel(label,{exact:true}).fill(value);await dialog.getByLabel(label,{exact:true}).press('Tab');};
  const materialRows=(await api('/api/materials')).items;
  const m65=materialRows.find(r=>r.technical_identity_id==='MAT-CORE-DURABAR-65-45-12'),m80=materialRows.find(r=>r.technical_identity_id==='MAT-CORE-DURABAR-80-55-06');
  try{
    assert((await api('/api/health')).network.qa_isolated,'Isolated QA only');
    const project=await json(await page.request.post(base+'/api/projects',{headers,data:{design:{schema_version:3,name:'[QA] Project engineering',block:{length:120,width:120,height:100,material:m65.display_name,material_id:m65.id},nets:[{id:'P',routing:'automatic'},{id:'T',routing:'automatic'}]}}}));
    await page.setViewportSize({width:1580,height:1040});await page.goto(base);
    await page.locator(`[data-project-id="${project.project_id}"]`).getByRole('button',{name:'Open CAD',exact:true}).click();await page.getByLabel('Engineering material',{exact:true}).waitFor();
    const forbidden=/Allowable material stress|Pressure safety factor|Minimum wall|Preferred wall margin|Preferred component face|Preferred port face/;
    assert(!forbidden.test(await page.locator('#inspector').innerText()),'Engineering rules remain in Block');
    await settings();assert(await dialog.getByLabel('Minimum wall / ligament (optional) / mm',{exact:true}).inputValue()==='','New project silently used 7 mm');
    await edit('Default design pressure / bar','250');await edit('Default flow / L/min','60');await edit('Pressure safety factor','2.5');await edit('Minimum wall / ligament (optional) / mm','5');await edit('Preferred wall margin (optional) / mm','3');
    assert(!(await dialog.innerText()).includes('Preferred component face'),'Generation preference in Project Settings');
    await page.screenshot({path:output+'/project-settings.png'});await close();await nets();
    assert((await dialog.innerText()).includes('Effective pressure: 250 bar — Project default'),'P did not inherit pressure');
    assert((await dialog.innerText()).includes('Effective flow: 60 L/min — Project default'),'P did not inherit flow');
    await edit('Pressure override / bar · T','30');await edit('Flow override / L/min · T','80');
    await dialog.getByText(/Effective pressure: 30 bar — Net override/).waitFor();await dialog.getByText(/Effective flow: 80 L\/min — Net override/).waitFor();
    await page.screenshot({path:output+'/net-overrides.png'});await close();await settings();await edit('Default design pressure / bar','300');await close();await nets();
    await dialog.getByText(/Effective pressure: 300 bar — Project default/).waitFor();assert((await dialog.innerText()).includes('Effective pressure: 30 bar — Net override'),'T override changed');await close();
    await page.getByLabel('Engineering material',{exact:true}).selectOption(m80.id);await settings();
    for(const [label,value]of [['Pressure safety factor','2.5'],['Minimum wall / ligament (optional) / mm','5'],['Preferred wall margin (optional) / mm','3'],['Default design pressure / bar','300']])assert(await dialog.getByLabel(label,{exact:true}).inputValue()===value,label+' reset by material');
    await dialog.getByLabel('Project unit preference',{exact:true}).selectOption('inch');assert((await dialog.innerText()).includes('Metric and inch standards may be mixed.'),'Unit scope unclear');await close();
    assert(await page.getByLabel('Length X / mm',{exact:true}).inputValue()==='120','Unit preference converted geometry');
    await page.getByRole('button',{name:'Save Project',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#dirty-dot')?.getAttribute('aria-label')==='Draft saved');
    const saved=await api('/api/projects/'+project.project_id);assert(saved.design.nets.find(n=>n.id==='P').pressure_bar===null&&saved.design.nets.find(n=>n.id==='P').flow_lpm===null,'Inheritance materialized');assert(saved.design.schema_version===3,'Project schema not v3');
    const mixed=[];
    for(const [preference,family,portQuery,native]of [['inch','Metric','ISO 6149','metric'],['metric','UNC','NPT','inch']]){
      await settings();await dialog.getByLabel('Project unit preference',{exact:true}).selectOption(preference);await close();
      await page.locator('#add-feature-trigger').click();await page.locator('#add-mounting').click();
      await dialog.getByLabel('Hole type',{exact:true}).selectOption('threaded');await dialog.getByLabel('Thread standard / family',{exact:true}).selectOption(family);
      const threadId=await dialog.getByLabel('Thread size / specification',{exact:true}).inputValue();assert(threadId,'Opposite-unit threads hidden');
      await page.screenshot({path:output+'/mixed-'+preference+'-mounting.png'});
      await dialog.getByRole('button',{name:'Add mounting hole',exact:true}).click();await dialog.waitFor({state:'hidden'});
      await page.locator('#add-feature-trigger').click();await page.locator('#add-port').click();
      await dialog.getByLabel('P · Port source',{exact:true}).selectOption('standard');await dialog.getByLabel('P · Native definition',{exact:true}).selectOption(native);
      await dialog.getByLabel('P · Search port definition',{exact:true}).fill(portQuery);await dialog.getByRole('button',{name:'Use for P',exact:true}).first().click();
      await dialog.getByText(/SQLite source-backed machining definition/).waitFor();await page.screenshot({path:output+'/mixed-'+preference+'-port.png'});
      await dialog.getByRole('button',{name:'Add port to draft',exact:true}).click();await dialog.waitFor({state:'hidden'});
      await page.getByRole('button',{name:'Save Project',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#dirty-dot')?.getAttribute('aria-label')==='Draft saved');
      const checked=await api('/api/projects/'+project.project_id),mount=checked.design.features.filter(f=>f.kind==='mounting').at(-1),port=checked.design.features.filter(f=>f.kind==='port').at(-1);
      assert(mount.thread_definition_id===threadId&&port.port_definition_id,'Mixed-unit definitions did not persist');
      assert(checked.design.block.length===120&&checked.design.block.width===120&&checked.design.block.height===100,'Preference changed CAD dimensions');
      mixed.push({preference,family,threadId,portDefinition:port.port_definition_id});
    }
    assert(errors.length===0,'Page errors: '+errors.join('; '));
    return {passed:true,projectId:project.project_id,savedDefaults:saved.design.project_defaults,nets:saved.design.nets.map(n=>({id:n.id,pressure:n.pressure_bar,flow:n.flow_lpm,velocity:n.velocity_limit,mode:n.drilling_mode})),mixed,errors};
  }catch(error){await page.screenshot({path:output+'/failure.png'});return {passed:false,error:error.message,errors};}
}
