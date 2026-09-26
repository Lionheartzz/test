async page=>{
  const base='__BASE_URL__',passId='__PASS_PROJECT__',conflictId='__CONFLICT_PROJECT__',output='__OUTPUT_DIR__';
  const errors=[],wrongOrigin=[],stages=[];let buildPosts=0;
  page.on('pageerror',error=>errors.push(error.message));
  page.on('dialog',dialog=>dialog.accept());
  await page.route('**/api/**',route=>{
    const url=route.request().url();
    if(!url.startsWith(base+'/api/')){wrongOrigin.push(url);return route.abort();}
    if(url.endsWith('/api/build')&&route.request().method()==='POST')buildPosts++;
    return route.continue();
  });
  let stage='Six current-build exports';
  const addFeature=async id=>{await page.locator('#add-feature-trigger').click();await page.locator('#'+id).click();await page.locator('#workflow-dialog').waitFor({state:'visible'});};
  try{
    await page.setViewportSize({width:1366,height:768});
    await page.goto(`${base}/?project=${passId}`);
    await page.waitForFunction(()=>document.querySelector('#status')?.textContent==='PASS');
    await page.locator('.export-panel summary').click();
    const exports=[['step-download','production.step'],['engineering-step-download','engineering.step'],['data-download','design.json'],['report-download','validation.md'],['chart-download','drill-chart.csv'],['manufacturing-download','manufacturing.json']];
    for(const [id,name] of exports){
      const link=page.locator('#'+id);
      if(await link.getAttribute('aria-disabled')!=='false'||!await link.getAttribute('href'))throw Error(`${name} is unavailable for a current PASS build`);
      const [download]=await Promise.all([page.waitForEvent('download',{timeout:120000}),link.click()]);
      await download.saveAs(`${output}/${name}`);
    }
    await page.screenshot({path:`${output}/studio-pass-exports-1366x768.png`});
    stages.push(stage);

    stage='Dirty export gate and Reload';
    await page.locator('#select-block').click();
    await page.locator('#inspector').getByLabel('Project name').fill('Unsaved UI acceptance draft');
    await page.locator('#inspector').getByLabel('Project name').press('Tab');
    await page.waitForFunction(()=>document.querySelector('#status')?.textContent==='DRAFT');
    for(const [id]of exports)if(await page.locator('#'+id).getAttribute('aria-disabled')!=='true'||await page.locator('#'+id).getAttribute('href'))throw Error(`${id} bypassed dirty export gate`);
    await page.evaluate(()=>{window.confirm=message=>{window.__isolatedConfirm=message;return true;};});
    await page.locator('#project-menu-trigger').click();await page.locator('#reload').click();
    await page.waitForFunction(()=>document.querySelector('#status')?.textContent==='PASS');
    if(!/Discard unsaved draft/.test(await page.evaluate(()=>window.__isolatedConfirm||'')))throw Error('Reload skipped dirty confirmation');
    stages.push(stage);

    stage='Feature creation and object actions';
    await addFeature('add-mounting');
    await page.locator('#workflow-content').getByRole('button',{name:'Add mounting hole'}).click();
    await page.locator('#workflow-dialog').waitFor({state:'hidden'});
    await page.waitForFunction(()=>document.querySelector('#selection-kind')?.textContent==='MOUNTING');
    if(!await page.locator('#inspector details.inspector-section > summary').getByText('Mounting specification',{exact:true}).count())throw Error('Mounting inspector group is missing');
    if(!/Mounting Hole 1/.test(await page.locator('#feature-tree [data-feature].active').innerText()))throw Error('Auto-generated mounting ID leaked into the Feature Tree');
    await page.locator('#inspector').getByRole('button',{name:'Duplicate'}).click();
    if(!/^MNT\d+$/.test(await page.locator('#feature-tree [data-feature].active').getAttribute('data-feature')))throw Error('Duplicated mounting hole used the wrong ID family');
    await page.locator('#inspector').getByRole('button',{name:'Suppress'}).click();
    await page.locator('#inspector').getByRole('button',{name:'Restore'}).click();
    await page.locator('#inspector').getByRole('button',{name:'Delete',exact:true}).click();
    await addFeature('add-port');
    await page.locator('#workflow-content').getByRole('button',{name:'Add port to draft'}).click();
    await page.locator('#workflow-dialog').waitFor({state:'hidden'});
    await page.waitForFunction(()=>document.querySelector('#selection-kind')?.textContent==='PORT');
    if(!await page.locator('#inspector details.inspector-section > summary').getByText('Hydraulic & machining',{exact:true}).count())throw Error('Port inspector group is missing');
    await addFeature('add-engraving');
    await page.locator('#workflow-content').getByRole('button',{name:'Add engraving'}).click();
    await page.locator('#workflow-dialog').waitFor({state:'hidden'});
    await addFeature('add-block-modifier');
    await page.locator('#workflow-content').getByRole('button',{name:'Add block machining'}).click();
    await page.locator('#workflow-dialog').waitFor({state:'hidden'});
    await addFeature('add-cavity');
    await page.locator('#workflow-content').getByRole('button',{name:'Create Custom Cavity'}).click();
    await page.locator('#workflow-content').getByRole('button',{name:'Save New Custom Cavity'}).click();
    await page.locator('#workflow-content').getByRole('button',{name:'Place this cavity'}).click();
    await page.locator('#workflow-content').getByRole('button',{name:'Add cavities to draft'}).click();
    await page.locator('#workflow-dialog').waitFor({state:'hidden'});
    await page.waitForFunction(()=>document.querySelector('#selection-kind')?.textContent==='CAVITY');
    if(!await page.locator('#inspector details.inspector-section > summary').getByText('Source machining info',{exact:true}).count())throw Error('Cavity source group is missing');
    if(buildPosts)throw Error('Creating features launched exact validation');
    await page.screenshot({path:`${output}/studio-feature-draft-1366x768.png`});
    await page.locator('#project-menu-trigger').click();await page.locator('#reload').click();
    await page.waitForFunction(()=>document.querySelector('#status')?.textContent==='PASS');
    stages.push(stage);

    stage='Clean external reload and dirty revision conflict';
    await page.goto(`${base}/?project=${conflictId}`);
    await page.waitForFunction(()=>document.querySelector('#project-name')?.textContent==='Phase 6 optimistic conflict fixture');
    await page.locator('#select-block').click();
    await page.locator('#inspector').getByLabel('Project name').fill('Local unsaved conflict draft');
    await page.locator('#inspector').getByLabel('Project name').press('Tab');
    const clean=await page.context().newPage();clean.on('pageerror',error=>errors.push(error.message));
    await clean.goto(`${base}/?project=${conflictId}`);
    const rival=await page.context().newPage();rival.on('pageerror',error=>errors.push(error.message));
    await rival.goto(`${base}/?project=${conflictId}`);
    await rival.locator('#select-block').click();
    await rival.locator('#inspector').getByLabel('Length X / mm').fill('101');
    await rival.locator('#inspector').getByLabel('Length X / mm').press('Tab');
    await rival.locator('#save-project').click();
    await rival.waitForFunction(()=>document.querySelector('#notice')?.textContent?.includes('Saved to Projects'),null,{timeout:15000});
    await rival.close();
    await clean.bringToFront();
    await clean.waitForFunction(()=>document.querySelector('#inspector input[aria-label="Length X / mm"]')?.value==='101',null,{timeout:15000});
    await clean.close();
    await page.bringToFront();
    await page.waitForFunction(()=>document.querySelector('#notice')?.textContent?.includes('Project changed on disk'),null,{timeout:15000});
    if(await page.locator('#inspector').getByLabel('Project name').inputValue()!=='Local unsaved conflict draft')throw Error('External update overwrote dirty draft');
    await page.locator('#save-project').click();
    await page.waitForFunction(()=>document.querySelector('#notice')?.textContent?.includes('Saved project changed'),null,{timeout:15000});
    if(await page.locator('#dirty-dot').getAttribute('aria-label')!=='Unsaved draft')throw Error('409 conflict cleared dirty draft');
    await page.screenshot({path:`${output}/studio-revision-conflict-1366x768.png`});
    stages.push(stage);

    if(errors.length||wrongOrigin.length)throw Error('Browser errors or off-origin request: '+JSON.stringify({errors,wrongOrigin}));
    return {passed:true,stage,stages,passId,conflictId,buildPosts,errors,wrongOrigin};
  }catch(error){
    await page.screenshot({path:`${output}/failure.png`}).catch(()=>{});
    return {passed:false,stage,stages,error:String(error),buildPosts,errors,wrongOrigin};
  }
}
