async page => {
  const base='__BASE_URL__',output='__OUTPUT_DIR__',dialog=page.locator('#workflow-dialog'),errors=[];
  const assert=(v,m)=>{if(!v)throw Error(m);};page.on('pageerror',e=>errors.push(e.message));
  page.removeAllListeners('response');
  let packet=null;page.on('response',async r=>{if(r.url().includes('/api/ai-design/jobs/')&&r.ok()){const j=await r.json();if(j?.result?.design)packet=j.result;}});
  const close=async()=>{await dialog.press('Escape');await dialog.waitFor({state:'hidden'});};
  try{
    assert((await(await page.request.get(base+'/api/health')).json()).network.qa_isolated,'Isolated QA only');
    // Start with the completed, transparently marked test analysis. No model call.
    if(await dialog.isHidden()){await page.getByRole('button',{name:'AI Design',exact:true}).click();await dialog.getByRole('heading',{name:'AI Design · Management',exact:true}).waitFor();}
    const create=dialog.getByRole('button',{name:'Create manifold draft',exact:true});
    if(await dialog.getByRole('heading',{name:'AI Design · Management',exact:true}).count()){await dialog.getByRole('heading',{name:'Generation QA',exact:true}).locator('..').getByRole('button',{name:'Open',exact:true}).click();await create.waitFor();}
    const returnToAnalysis=dialog.getByRole('button',{name:'Return to analysis',exact:true});if(await returnToAnalysis.count()){await returnToAnalysis.click();await create.waitFor();}
    if(await create.count())await create.click();await dialog.getByLabel('Preferred valve / cartridge face',{exact:true}).waitFor();
    if(!await dialog.getByLabel('VALVE_RV1 · window port1 → schematic port',{exact:true}).count()){
      await dialog.getByText('Search existing cavities',{exact:true}).click();await dialog.getByLabel('Library search · VALVE_RV1',{exact:true}).fill('VC08-2');
      await dialog.getByRole('button',{name:'Search library · VALVE_RV1',exact:true}).click();await dialog.getByRole('button',{name:'Choose VC08-2',exact:true}).first().click();
    }
    await dialog.getByLabel('VALVE_RV1 · window port1 → schematic port',{exact:true}).selectOption('RV1_P');
    await dialog.getByLabel('VALVE_RV1 · window port2 → schematic port',{exact:true}).selectOption('RV1_T');
    await dialog.getByLabel('Cavity / mapping decision · VALVE_RV1',{exact:true}).fill('QA explicit source cavity and P/T mapping; test draft only.');
    for(const port of ['EXT_P','EXT_T']){
      const choose=dialog.getByRole('button',{name:'Choose One-off Custom Straight Bore · '+port,exact:true});if(await choose.count())await choose.click();
      await dialog.getByLabel('Provisional straight-bore decision · '+port,{exact:true}).fill('QA explicitly approves one-off geometry; no standard identity inferred.');
    }
    await dialog.getByLabel('Preferred valve / cartridge face',{exact:true}).selectOption('front');
    await dialog.getByLabel('Preferred external port face',{exact:true}).selectOption('left');
    await dialog.getByLabel('Placement override decision',{exact:true}).fill('QA uses front cavity and left ports for this generated draft.');
    await dialog.getByText('Draft geometry assumptions and search budget',{exact:true}).click();
    await dialog.getByLabel('Maximum layout attempts',{exact:true}).fill('1');
    await dialog.getByRole('button',{name:'Recheck choices and requirements',exact:true}).click();
    await dialog.getByRole('heading',{name:'AI generation placement preferences',exact:true}).waitFor();
    assert(await dialog.locator('.ai-blocked').count()===0,'Generation decisions remain unresolved');
    await page.screenshot({path:output+'/ai-generation-preferences.png'});
    await dialog.getByRole('button',{name:'Generate editable 3D draft',exact:true}).click();
    await dialog.getByRole('button',{name:'Open draft in Manifold Studio',exact:true}).waitFor({timeout:180000});
    assert(packet?.design,'No actual generation packet');
    const cavity=packet.design.features.find(f=>f.kind==='cavity'),ports=packet.design.features.filter(f=>f.kind==='port');
    assert(cavity.face==='front'&&ports.every(f=>f.face==='left'),'Preferences were not used for generated geometry');
    assert(!packet.design.constraints.preferred_component_faces.length&&!Object.keys(packet.design.constraints.preferred_port_faces).length,'Preferences persisted as engineering constraints');
    await dialog.getByRole('button',{name:'Open draft in Manifold Studio',exact:true}).click();await dialog.waitFor({state:'hidden'});
    assert(!/Preferred component face|Preferred port face|Pressure safety factor|Minimum wall/.test(await page.locator('#inspector').innerText()),'Generation/rules leaked into Block');
    await page.screenshot({path:output+'/ai-generated-model.png'});
    const stored=page.waitForResponse(r=>r.url()===base+'/api/projects'&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Save Project',exact:true}).click();const saved=await(await stored).json();
    await page.waitForFunction(()=>document.querySelector('#dirty-dot')?.getAttribute('aria-label')==='Draft saved');
    const pose=JSON.stringify(saved.design.features.map(f=>[f.id,f.face,f.u,f.v]));
    await page.getByRole('button',{name:'AI Design',exact:true}).click();
    await dialog.getByRole('heading',{name:'Generation QA',exact:true}).locator('..').getByRole('button',{name:'Open',exact:true}).click();await create.waitFor();
    await create.click();
    await dialog.getByLabel('Preferred valve / cartridge face',{exact:true}).selectOption('back');
    await dialog.getByLabel('Preferred external port face',{exact:true}).selectOption('right');await close();
    const after=await(await page.request.get(base+'/api/projects/'+saved.project_id)).json();
    assert(JSON.stringify(after.design.features.map(f=>[f.id,f.face,f.u,f.v]))===pose,'Later preference moved existing geometry');
    for(const f of saved.design.features){await page.locator(`[data-feature="${f.id}"]`).click();assert(await page.getByLabel('Face',{exact:true}).inputValue()===f.face,'Live draft face moved');assert(Number(await page.getByLabel('Position U / mm',{exact:true}).inputValue())===f.u&&Number(await page.getByLabel('Position V / mm',{exact:true}).inputValue())===f.v,'Live draft position moved');}
    assert(errors.length===0,'Page errors: '+errors.join('; '));
    return {passed:true,projectId:saved.project_id,generationId:packet.id,faces:{cavity:cavity.face,ports:ports.map(f=>f.face)},existingPoseUnchanged:true,errors};
  }catch(e){await page.screenshot({path:output+'/ai-generation-failure.png'});return {passed:false,error:e.message,errors};}
}
