async page => {
  const base='__BASE_URL__',output='__OUTPUT_DIR__',headers={'X-PMC-Request':'local-console'},stages=[],errors=[];
  let stage='Setup';const assert=(value,message)=>{if(!value)throw Error(message);};
  page.on('pageerror',error=>errors.push(error.message));
  const json=async response=>{assert(response.ok(),await response.text());return response.json();};
  const api=path=>page.request.get(base+path).then(json),dialog=page.locator('#workflow-dialog');
  const close=async()=>{await dialog.press('Escape');await dialog.waitFor({state:'hidden'});};
  const screenshot=async name=>page.screenshot({path:output+'/'+name+'.png',fullPage:false});
  try{
    assert((await api('/api/health')).network.qa_isolated,'Use isolated QA server only');
    const materials=(await api('/api/materials')).items,all=(await api('/api/materials?include_legacy=true')).items;
    const ductile=materials.find(r=>r.technical_identity_id==='MAT-CORE-DURABAR-65-45-12');
    const plate=materials.find(r=>r.technical_identity_id==='MAT-CORE-7075-T651-PLATE');
    assert(ductile&&plate,'Expected precise core identities');
    await page.setViewportSize({width:1580,height:1040});await page.goto(base);
    await page.getByText('ENGINEERING DB READY',{exact:true}).waitFor();
    const secure=await page.evaluate(()=>isSecureContext);assert(secure===base.includes('127.0.0.1'),'Secure context mismatch');
    stage='New Home / Guided selector';
    const home=page.getByRole('region',{name:'Engineering Home'}),homeMaterials=home.getByLabel('Material',{exact:true});
    await homeMaterials.locator('option').last().waitFor({state:'attached'});
    await page.waitForFunction(()=>document.querySelector('.home-shell select[aria-label="Material"]')?.dataset.loaded==='true'||document.querySelector('[aria-label="Material"][data-loaded="true"]'));
    const homeNames=await homeMaterials.locator('option').evaluateAll(rows=>rows.filter(r=>r.value).map(r=>r.textContent));
    assert(homeNames.length===materials.length&&!homeNames.some(n=>/Legacy|^Aluminum$|^DuraBar$/.test(n)),'Generic legacy in new Home selector');
    await screenshot('home-core-selector');
    await home.getByRole('button',{name:'New Manifold',exact:true}).click();
    await dialog.getByRole('combobox',{name:/Material/}).waitFor();
    const guidedText=await dialog.innerText();assert(!guidedText.includes('Legacy unspecified'),'Guided contains legacy identity');
    await screenshot('guided-core-selector');await close();stages.push(stage);
    const projects=[];
    for(const [material_id,material] of [[null,'Unspecified'],['material_1','Aluminum'],['material_2','DuraBar']]){
      projects.push(await json(await page.request.post(base+'/api/projects',{headers,data:{design:{schema_version:2,name:'Core material QA '+(material_id||'new')+' '+base,
        project_context:'metric',block:{length:160,width:100,height:100,material,material_id}}}})));
    }
    await page.reload();await page.getByText('ENGINEERING DB READY',{exact:true}).waitFor();
    const open=async id=>{await page.locator(`[data-project-id="${id}"]`).getByRole('button',{name:'Open CAD',exact:true}).click();await page.getByLabel('Engineering material',{exact:true}).waitFor();};
    stage='Old legacy IDs load without automatic remapping';
    for(const [index,id] of [[1,'material_1'],[2,'material_2']]){
      await open(projects[index].project_id);
      const input=page.getByLabel('Engineering material',{exact:true});
      assert(await input.inputValue()===id,'Legacy material ID changed');
      const choices=await input.locator('option').evaluateAll(rows=>rows.filter(r=>r.value).map(r=>({id:r.value,name:r.textContent})));
      assert(choices.filter(r=>r.id==='material_1'||r.id==='material_2').length===1,'Other legacy choice leaked into old-project selector');
      assert(choices.find(r=>r.id===id).name.startsWith('Legacy unspecified'),'Legacy label unclear');
      const stored=await api('/api/projects/'+projects[index].project_id);assert(stored.design.block.material_id===id,'Stored legacy remapped');
      await screenshot('legacy-'+id);await page.locator('#projects-open').click();
    }
    stages.push(stage);
    stage='Precise core selection, facts and no invented allowable';await open(projects[0].project_id);
    const selector=page.getByLabel('Engineering material',{exact:true});
    const options=await selector.locator('option').evaluateAll(rows=>rows.filter(r=>r.value).map(r=>r.value));
    assert(options.length===materials.length&&!options.includes('material_1')&&!options.includes('material_2'),'New Model includes generic legacy');
    await selector.selectOption(ductile.id);
    await page.getByText(/Yield Strength: 310\.264 MPa · Source-backed · minimum/).waitFor();
    assert(await page.getByLabel('Allowable material stress / MPa',{exact:true}).inputValue()==='','Strength became allowable stress');
    assert(await page.getByLabel('Raw stock / standard blank',{exact:true}).locator('option').count()===1,'Supplier stock entered engineering stock');
    await screenshot('ductile-core-material');
    await page.getByRole('button',{name:'Save Project',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#dirty-dot')?.getAttribute('aria-label')==='Draft saved');
    assert((await api('/api/projects/'+projects[0].project_id)).design.block.material_id===ductile.id,'Precise ID did not persist');
    await selector.selectOption(plate.id);await page.getByText(/Yield Strength: 503 MPa · Source-backed · typical/).waitFor();
    await screenshot('7075-plate');stages.push(stage);
    stage='Primary evidence, form restrictions and research-only reasons';
    await page.locator('#inspector').getByRole('button',{name:'View technical evidence',exact:true}).click();
    await dialog.getByRole('heading',{name:'Primary identity sources',exact:true}).waitFor();
    assert((await dialog.innerText()).includes('Block stock form: Plate'),'Plate source scope missing');
    assert(await dialog.getByRole('button',{name:/^(Place|Bind|Use)/}).count()===0,'Evidence grants execution');
    const link=dialog.getByRole('link',{name:'Open source',exact:true}).first(),href=await link.getAttribute('href');
    assert(href.startsWith('https://'),'Primary source URL incomplete');
    const [popup]=await Promise.all([page.waitForEvent('popup'),link.click()]);await popup.waitForLoadState('domcontentloaded');
    assert(popup.url().startsWith('https://'),'Primary source did not open');await popup.close();
    await screenshot('7075-primary-evidence');
    await dialog.getByRole('button',{name:'Back to Materials & Stock',exact:true}).click();
    await dialog.getByLabel('Search Materials & Stock',{exact:true}).fill('1045');
    await dialog.getByRole('heading',{name:/^1045/}).waitFor();await dialog.getByRole('button',{name:'View Detail',exact:true}).click();
    await dialog.getByText(/Research-only material · Exact normalized 1045 bar product standard/).waitFor();await screenshot('1045-research-only');
    await dialog.getByRole('button',{name:'Back to Materials & Stock',exact:true}).click();
    await dialog.getByLabel('Search Materials & Stock',{exact:true}).fill('Legacy unspecified');
    await dialog.getByRole('heading',{name:'Legacy unspecified Aluminum',exact:true}).waitFor();
    assert((await dialog.innerText()).includes('Legacy unspecified Dura-Bar'),'Library omitted legacy IDs');await screenshot('legacy-library');stages.push(stage);
    assert(errors.length===0,'Page errors: '+errors.join('; '));
    return {passed:true,base,secureContext:secure,selectableCount:materials.length,runtimeBrowseCount:all.length,stages,errors};
  }catch(error){await screenshot('failure');return {passed:false,base,stage,error:error.message,stages,errors};}
}
