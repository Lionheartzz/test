async page=>{
  const root='__PROJECT_ROOT__',base='__BASE_URL__',design=__DESIGN__;
  design.name='Interactive cavity move QA '+Date.now();
  const headers={'X-PMC-Request':'local-console'},errors=[],requests=[],timings=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().includes('/api/preview'))requests.push(r.url());});
  page.on('dialog',d=>d.accept());
  const created=await page.request.post(base+'/api/projects',{headers,data:{design}});
  if(!created.ok())throw Error(await created.text());
  const saved=await created.json();
  try{
    await page.goto(base);await page.setViewportSize({width:1440,height:1000});
    await page.getByRole('article').filter({hasText:design.name}).getByRole('button',{name:'Open',exact:true}).click();
    const ready=()=>page.waitForFunction(()=>document.querySelector('#viewport').dataset.previewState==='exact-proposal',{},{timeout:16000});
    await ready();
    await page.locator('#feature-tree [data-feature="CV2"]').click();
    await page.getByRole('combobox',{name:'View face',exact:true}).selectOption('front');
    await page.getByRole('slider',{name:'Stock opacity',exact:true}).evaluate(e=>{e.value='22';e.dispatchEvent(new Event('input',{bubbles:true}));});
    const before=await page.locator('#viewport').evaluate(e=>({mode:e.dataset.viewMode,opacity:e.dataset.stockOpacity}));
    const edit=async u=>{const f=page.getByRole('spinbutton',{name:'Position U / mm',exact:true});await f.fill(String(u));await f.press('Tab');};
    for(const u of [106,97,107]){
      const start=Date.now();await edit(u);
      if(await page.locator('#viewport').getAttribute('data-preview-state')!=='approximate')throw Error('Immediate live feedback missing');
      await page.waitForFunction(()=>document.querySelector('#viewport').dataset.previewState==='computing');
      await ready();timings.push({u,elapsed_ms:Date.now()-start});
      if(await page.getByRole('spinbutton',{name:'Position U / mm',exact:true}).inputValue()!==String(u))throw Error('Selection/position changed');
      const after=await page.locator('#viewport').evaluate(e=>({mode:e.dataset.viewMode,opacity:e.dataset.stockOpacity}));
      if(JSON.stringify(before)!==JSON.stringify(after))throw Error('Stock or mode changed');
    }
    if(requests.some(url=>url===base+'/api/preview'))throw Error('Repeated fast/exact worker pipeline remains');
    await page.screenshot({path:root+'/output/playwright/interactive-moved-exact.png',fullPage:true});
    // Distinct unavailable state, with the actual reason and last view retained.
    await page.route('**/api/preview-solid',route=>route.fulfill({status:200,contentType:'application/x-ndjson',body:'{"type":"error","status":504,"detail":"Exact preview exceeded 15 seconds; worker stopped (QA injection)."}\n'}));
    await edit(105);
    await page.waitForFunction(()=>document.querySelector('#viewport').dataset.previewState==='unavailable');
    if(!await page.locator('.viewport-loading').isHidden())throw Error('Stuck computing state');
    if(!await page.getByRole('button',{name:'Save Project',exact:true}).isEnabled())throw Error('Saving disabled');
    if(!(await page.locator('#model-info').innerText()).includes('exceeded 15 seconds'))throw Error('Actual timeout cause hidden');
    await page.screenshot({path:root+'/output/playwright/interactive-unavailable.png',fullPage:true});
    await page.unroute('**/api/preview-solid');await edit(106);await ready();
    if((await page.locator('#notice').innerText()).includes('exceeded'))throw Error('Old timeout error remained after recovery');
    if(errors.length)throw Error(errors.join('\n'));
    const result={passed:true,timings,previewRequests:requests.length,separateFastRequests:0,context:before};
    return result;
  }catch(error){
    await page.screenshot({path:root+'/output/playwright/interactive-failure.png',fullPage:true});
    return {passed:false,error:String(error),timings,errors,requests};
  }finally{
    if(await page.locator('#save-project').isEnabled()){
      await page.locator('#save-project').click();
      await page.waitForFunction(()=>document.querySelector('#status').textContent!=='DRAFT');
    }
    await page.goto(base);
    const current=await (await page.request.get(base+'/api/projects/'+saved.project_id)).json();
    const removed=await page.request.post(base+'/api/projects/'+saved.project_id+'/delete',{headers,data:{expected_revision:current.revision,confirm_name:design.name}});
    if(!removed.ok())throw Error('QA project cleanup failed: '+await removed.text());
  }
}
