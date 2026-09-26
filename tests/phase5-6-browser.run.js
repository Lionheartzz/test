async page=>{
  const base='__BASE_URL__',firstId='__FIRST_PROJECT__',secondId='__SECOND_PROJECT__',output='__OUTPUT_DIR__';
  const errors=[],wrongOrigin=[],writes=[],renders=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',route=>{
    const request=route.request(),url=request.url();
    if(!url.startsWith(base+'/api/')){wrongOrigin.push(url);return route.abort();}
    if(request.method()==='POST'){
      if(/\/render$/.test(url))renders.push(url);
      else writes.push(url);
    }
    return route.continue();
  });
  let stage='Studio project switch';
  try{
    await page.setViewportSize({width:1366,height:768});
    await page.goto(base);
    await page.getByRole('article').filter({hasText:'Two cavity interactive regression'}).getByRole('button',{name:'Open',exact:true}).click();
    await page.locator('#viewport canvas').waitFor({state:'visible'});
    const firstFeature=page.locator('#feature-tree [data-feature]').first();
    await firstFeature.click();
    if(await page.locator('#viewport').getAttribute('data-local-gizmo')!==await firstFeature.getAttribute('data-feature'))throw Error('Selected feature local axes were not visible');
    await page.screenshot({path:`${output}/studio-local-gizmo-1366x768.png`});
    const firstSection=page.locator('#inspector details.inspector-section').first();
    await firstSection.locator('summary').click();
    if(await firstSection.evaluate(node=>node.open))throw Error('Inspector section did not collapse');
    await page.locator('#feature-tree [data-feature]').nth(1).click();
    await firstFeature.click();
    if(await page.locator('#inspector details.inspector-section').first().evaluate(node=>node.open))throw Error('Inspector fold state was lost on redraw');
    await page.locator('#inspector details.inspector-section').first().locator('summary').click();
    if(!await page.locator('#inspector details.inspector-section').first().evaluate(node=>node.open))throw Error('Inspector section did not reopen');
    await page.locator('#projection-toggle').click();
    await page.locator('#isolate-selection').click();
    if(await page.locator('#viewport').getAttribute('data-isolation')!=='feature')throw Error('Owner feature isolation did not activate');
    await page.locator('#display-menu-trigger').click();
    await page.locator('#clip-enabled').check();
    if(await page.locator('#viewport').getAttribute('data-clipping')==='off')throw Error('Section did not activate');
    await page.locator('#projects-open').click();
    await page.getByRole('article').filter({hasText:'Phase 5-6 isolated switch target'}).getByRole('button',{name:'Open',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#project-name')?.textContent==='Phase 5-6 isolated switch target');
    if(await page.locator('#viewport').getAttribute('data-isolation')!=='none'||await page.locator('#viewport').getAttribute('data-clipping')!=='off')throw Error('Project switch leaked transient Viewer state');
    if(await page.locator('#projection-toggle').innerText()!=='Orthographic')throw Error('Project switch lost session projection');
    if(await page.locator('#dirty-dot').getAttribute('aria-label')!=='Draft saved')throw Error('Layout/navigation dirtied a project');

    stage='Drawing creation and responsive shell';
    await page.goto(`${base}/drawing.html?project=${firstId}`);
    await page.locator('#project-title').waitFor({state:'visible'});
    await page.locator('#create').click();
    await page.locator('#modal').waitFor({state:'visible'});
    await page.getByRole('button',{name:'Create engineering drawing'}).click();
    await page.locator('#paper-container svg').waitFor({state:'visible',timeout:120000});
    const drawingUrl=page.url();
    if(!drawingUrl.includes('drawing='))throw Error('Drawing was not opened after its job completed');
    await page.screenshot({path:`${output}/drawing-created-1366x768.png`});
    const initialState=await page.locator('#document-state').innerText();
    await page.setViewportSize({width:900,height:800});
    await page.locator('#drawing-tree-toggle').click();
    if(await page.locator('body').getAttribute('data-drawing-left-open')!=='true')throw Error('Sheets overlay did not open');
    await page.locator('#drawing-properties-toggle').click();
    if(await page.locator('body').getAttribute('data-drawing-left-open')!=='false'||await page.locator('body').getAttribute('data-drawing-right-open')!=='true')throw Error('Drawing overlays were not mutually exclusive');
    await page.locator('.drawing-backdrop').click({position:{x:450,y:300}});
    if(await page.locator('#document-state').innerText()!==initialState)throw Error('Drawing layout changed edit state');
    await page.locator('#fit').click();
    await page.screenshot({path:`${output}/drawing-created-900x800.png`});

    stage='Drawing menus, native Escape and editing';
    const menu=label=>page.locator('.drawing-menu-host').filter({hasText:label}).locator('.drawing-menu-trigger');
    const rendersBefore=renders.length;
    await menu('Edit').click();await page.keyboard.press('Escape');
    if(renders.length!==rendersBefore)throw Error('Closing a Drawing menu triggered paper regeneration');
    if(!await menu('Edit').evaluate(node=>node===document.activeElement))throw Error('Menu Escape did not restore focus');
    await menu('Insert').click();await page.locator('#view').click();
    if(!await page.locator('#modal').isVisible())throw Error('View modal did not open');
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>!document.querySelector('#modal')?.open&&document.activeElement?.textContent?.startsWith('Insert'));
    await menu('Add annotation').click();await page.locator('#text').click();
    if(!/Unsaved/.test(await page.locator('#document-state').innerText()))throw Error('Adding a note did not mark Drawing dirty');
    await menu('Edit').click();await page.locator('#undo').click();
    if(await page.locator('#objects').getByText('New note').count())throw Error('Undo did not remove the note');
    await menu('Edit').click();await page.locator('#redo').click();
    if(!await page.locator('#objects').getByText('New note').count())throw Error('Redo did not restore the note');
    await page.locator('#save').click();
    await page.waitForFunction(()=>!document.querySelector('#document-state')?.textContent?.includes('Unsaved'));
    await page.reload();
    await page.locator('#drawing-tree-toggle').click();
    await page.locator('#objects').getByText('New note').waitFor({state:'visible'});

    stage='Isolated PDF and exact-build busy lock';
    const [download]=await Promise.all([
      page.waitForEvent('download',{timeout:120000}),
      page.locator('#pdf').click(),
    ]);
    if(download.suggestedFilename()!=='drawing.pdf')throw Error('Drawing PDF filename changed');
    await download.saveAs(`${output}/drawing-draft.pdf`);
    await page.goto(`${base}/?project=${firstId}`);
    await page.locator('#build').waitFor({state:'visible'});
    await page.locator('#build').click();
    await page.waitForFunction(()=>document.body.classList.contains('busy'));
    for(const id of ['projects-open','save-project','build','add-cavity']){
      if(!await page.locator('#'+id).isDisabled())throw Error(`${id} remained enabled during exact validation`);
    }
    await page.waitForFunction(()=>!document.body.classList.contains('busy'),null,{timeout:120000});
    if(await page.locator('#projects-open').isDisabled()||await page.locator('#save-project').isDisabled())throw Error('Commands did not recover after exact validation');
    if(await page.locator('#dirty-dot').getAttribute('aria-label')!=='Draft saved')throw Error('Validate left a dirty draft');
    if(errors.length||wrongOrigin.length)throw Error('Browser errors or request outside isolated service: '+JSON.stringify({errors,wrongOrigin}));
    return {passed:true,stage,firstId,secondId,drawingUrl,writes:writes.length,renders:renders.length,errors,wrongOrigin};
  }catch(error){
    await page.screenshot({path:`${output}/failure.png`}).catch(()=>{});
    return {passed:false,stage,error:String(error),writes:writes.length,renders:renders.length,errors,wrongOrigin};
  }
}
