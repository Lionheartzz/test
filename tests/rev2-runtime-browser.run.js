async page => {
  const base='__BASE_URL__',output='__OUTPUT_DIR__',stages=[],errors=[];let stage='setup';
  const assert=(value,message)=>{if(!value)throw Error(message);};
  const headers={'X-PMC-Request':'local-console'},dialog=page.locator('#workflow-dialog');
  page.on('pageerror',error=>errors.push(error.message));
  const json=async response=>{assert(response.ok(),await response.text());return response.json();};
  const api=path=>page.request.get(base+path).then(json);
  const close=async()=>{await dialog.press('Escape');await dialog.waitFor({state:'hidden'});};
  const screenshot=async name=>{await page.screenshot({path:output+'/'+name+'.png',fullPage:false});};
  try{
    assert((await api('/api/health')).network.qa_isolated===true,'Use isolated QA server only; no normal project writes');
    const materials=(await api('/api/materials')).items,m6061=materials.find(m=>m.technical_identity_id==='MAT-6061'),m6082=materials.find(m=>m.technical_identity_id==='MAT-6082');
    assert(m6061&&m6082,'Promoted grades missing');
    const sun=(await api('/api/cartridges?q=Sun%20RDFA3&limit=20')).items.find(r=>r.model==='RDFA3');assert(sun,'Source cartridge missing');
    const created=await json(await page.request.post(base+'/api/projects',{headers,data:{design:{schema_version:2,name:'REV2 runtime '+base,project_context:'metric',
      block:{length:160,width:100,height:100,material:'Aluminum',material_id:'material_1'},
      nets:[{id:'P',color:'#ef5959',pressure_bar:300,flow_lpm:20}],
      schematic_intent:{components:[{id:'SCV1',label:'Runtime fact review',cartridge_id:sun.id,interface_nets:{port1:'P'}}]}}}}));
    await page.setViewportSize({width:1580,height:1040});await page.goto(base);
    await page.getByText('ENGINEERING DB READY',{exact:true}).waitFor();
    const secure=await page.evaluate(()=>isSecureContext);assert(secure===base.includes('127.0.0.1'),'LAN secure context mismatch');
    await page.locator(`[data-project-id="${created.project_id}"]`).getByRole('button',{name:'Open CAD',exact:true}).click();
    await page.getByLabel('Engineering material',{exact:true}).waitFor();
    stage='Material identities, defaults and raw stock';
    const select=page.getByLabel('Engineering material',{exact:true});
    assert((await select.locator('option').count())===materials.length+1,'Selector differs from runtime material API');
    await select.selectOption(m6061.id);
    assert(await page.getByLabel('Allowable material stress / MPa',{exact:true}).inputValue()==='','Yield converted into allowable');
    assert(await page.getByLabel('Raw stock / standard blank',{exact:true}).locator('option').count()===1,'Supplier inventory became engineering stock');
    assert(!/Material engineering data|Conditional.reference observations|View technical evidence|Supplier stock references|Treatment references|Source-backed/.test(await page.locator('#inspector').innerText()),'Material research leaked into Model');
    await screenshot('model-material');stages.push(stage);
    stage='Overrides survive rerender and stable IDs persist';
    for(const [label,value] of [['Allowable material stress / MPa','123'],['Pressure safety factor','3'],['Preferred extra wall margin / mm','6'],['Minimum wall / mm','9']]){
      await page.getByLabel(label,{exact:true}).fill(value);await page.getByLabel(label,{exact:true}).press('Tab');
    }
    await page.getByRole('button',{name:'Block Envelope · material · rules',exact:true}).click();
    assert(await page.getByLabel('Allowable material stress / MPa',{exact:true}).inputValue()==='123','Override lost on rerender');
    await page.getByRole('button',{name:'Save Project',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#dirty-dot')?.getAttribute('aria-label')==='Draft saved');
    const saved=await api('/api/projects/'+created.project_id);assert(saved.design.block.material_id===m6061.id&&saved.design.block.material===m6061.display_name,'Stable material identity not saved');
    assert(saved.design.rules.allowable_stress_mpa===123&&saved.design.rules.minimum_wall===9,'Saved override differs');
    await screenshot('material-override');stages.push(stage);
    stage='Changing material applies defaults once';await select.selectOption(m6082.id);
    assert(await page.getByLabel('Allowable material stress / MPa',{exact:true}).inputValue()==='','New material retained old stress');
    for(const [label,value] of [['Pressure safety factor','2'],['Preferred extra wall margin / mm','4'],['Minimum wall / mm','7']])assert(await page.getByLabel(label,{exact:true}).inputValue()===value,label+' default wrong');
    stages.push(stage);
    stage='Material evidence and research actionability';await page.getByRole('button',{name:/^Engineering(?: \d+)?$/}).click();await page.getByRole('button',{name:'Engineering Library',exact:true}).click();
    await dialog.locator('.library-category-card').filter({has:page.getByRole('heading',{name:'Materials & Stock',exact:true})}).getByRole('button',{name:'Open →',exact:true}).click();
    await dialog.getByLabel('Search Materials & Stock',{exact:true}).fill('6082');await dialog.getByRole('button',{name:'View Detail',exact:true}).click();
    await dialog.getByText('Engineering material · Available in Model material selector',{exact:true}).waitFor();
    assert(await dialog.getByRole('button',{name:/^(Place|Bind|Use)/}).count()===0,'Evidence offers an execution action');
    await screenshot('material-library');await dialog.getByRole('button',{name:'Back to Materials & Stock',exact:true}).click();
    await dialog.getByLabel('Search Materials & Stock',{exact:true}).fill('7075');
    await dialog.getByRole('button',{name:'View Detail',exact:true}).waitFor();await dialog.getByRole('button',{name:'View Detail',exact:true}).click();
    await dialog.getByText(/Research-only material · Standard applicability/).waitFor();await screenshot('research-only-material');await close();stages.push(stage);
    stage='Cartridge engineering review and schematic facts';await page.getByRole('button',{name:/^Engineering(?: \d+)?$/}).click();await page.locator('#review-open').click();
    await dialog.getByText(/Required 300 bar is within sourced maximum working pressure 344.7 bar/).waitFor();
    assert((await dialog.innerText()).includes('maximum flow unresolved'),'Relevant missing flow gap not visible');
    await screenshot('engineering-review');await dialog.getByRole('button',{name:'Open Schematic Intent',exact:true}).click();
    await dialog.getByText('Maximum Working Pressure: 344.7 bar · Source-backed',{exact:true}).waitFor();await screenshot('schematic-facts');await close();stages.push(stage);
    assert(errors.length===0,'Browser errors: '+errors.join('; '));
    return {passed:true,base,secureContext:secure,stages,materialCount:materials.length,projectId:created.project_id,materialId:m6061.id,errors};
  }catch(error){await screenshot('failure');return {passed:false,base,stage,error:error.message,stages,errors};}
}
