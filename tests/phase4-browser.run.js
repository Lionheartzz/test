async page=>{
  const base='__BASE_URL__',output='__OUTPUT_DIR__',savedDrawing='__SAVED_DRAWING_URL__',fixtureName='__FIXTURE_NAME__';
  const errors=[],requests=[],workerCancels=[],renderReads=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',route=>{
    if(route.request().method()!=='GET'){
      const request=`${route.request().method()} ${route.request().url()}`;
      if(route.request().method()==='POST'&&/\/api\/drawings\/[0-9a-f]{32}\/[0-9a-f]{32}\/render$/.test(route.request().url())){
        renderReads.push(request);return route.continue();
      }
      if(route.request().url().endsWith('/api/preview-cancel'))workerCancels.push(request);else requests.push(request);
      return route.abort();
    }
    return route.continue();
  });
  const dimensions=[];
  const capture=async(name,width,height)=>{
    await page.setViewportSize({width,height});
    const metrics=await page.evaluate(()=>({innerWidth,innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,workspaceHeight:document.querySelector('.workspace,.drawing-workspace')?.getBoundingClientRect().height||0,paperHeight:document.querySelector('#paper-viewport')?.getBoundingClientRect().height||0}));
    if(metrics.scrollHeight>height+2||metrics.scrollWidth>width+2)throw Error(`${name}: whole page overflow ${JSON.stringify(metrics)}`);
    await page.screenshot({path:`${output}/${name}.png`});
    dimensions.push({name,...metrics});
  };
  try{
    await page.goto(base);
    await page.setViewportSize({width:1366,height:768});
    await page.getByRole('searchbox',{name:'Search saved projects'}).fill(fixtureName);
    const project=page.locator('[data-project-id]').filter({hasText:fixtureName});
    await project.waitFor({state:'visible'});
    await project.getByRole('button',{name:'Open CAD',exact:true}).click();
    await page.locator('#viewport canvas').waitFor({state:'visible'});
    for(const [name,w,h] of [['studio-1366x768',1366,768],['studio-1920x1080',1920,1080],['studio-2560x1440',2560,1440],['studio-1100x800',1100,800],['studio-900x800',900,800]])await capture(name,w,h);
    const previousLayout=await page.evaluate(()=>{
      const key='pmc:studio-layout:v1',previous=localStorage.getItem(key);
      localStorage.setItem(key,JSON.stringify({left:308,right:412,drawer:280,leftCollapsed:false,rightCollapsed:false}));
      return previous;
    });
    await page.reload();
    await page.getByRole('searchbox',{name:'Search saved projects'}).fill(fixtureName);
    await page.locator('[data-project-id]').filter({hasText:fixtureName}).getByRole('button',{name:'Open CAD',exact:true}).click();
    const restored=await page.locator('.workspace').evaluate(node=>({left:node.style.getPropertyValue('--left-width'),right:node.style.getPropertyValue('--right-width')}));
    if(restored.left!=='308px'||restored.right!=='412px')throw Error('Studio v1 layout was not restored: '+JSON.stringify(restored));
    await page.evaluate(previous=>{const key='pmc:studio-layout:v1';if(previous===null)localStorage.removeItem(key);else localStorage.setItem(key,previous);},previousLayout);
    await page.reload();
    await page.getByRole('searchbox',{name:'Search saved projects'}).fill(fixtureName);
    await page.locator('[data-project-id]').filter({hasText:fixtureName}).getByRole('button',{name:'Open CAD',exact:true}).click();
    await page.locator('#viewport canvas').waitFor({state:'visible'});
    await page.setViewportSize({width:1366,height:768});
    const leftBefore=Number(await page.locator('#left-split').getAttribute('aria-valuenow'));
    await page.locator('#left-split').focus();await page.keyboard.press('ArrowRight');
    if(Number(await page.locator('#left-split').getAttribute('aria-valuenow'))!==leftBefore+10)throw Error('Keyboard separator did not resize the tree');
    await page.locator('#reset-layout').click();
    if(await page.evaluate(()=>localStorage.getItem('pmc:studio-layout:v1'))!==null)throw Error('Reset layout did not clear only the v1 layout key');
    await page.locator('#left-toggle').click();
    if(await page.locator('.workspace').getAttribute('data-left-collapsed')!=='true')throw Error('Feature Tree did not collapse');
    await page.locator('#left-restore').click();
    if(await page.locator('.workspace').getAttribute('data-left-collapsed')!=='false')throw Error('Feature Tree did not restore');
    await page.locator('#right-toggle').click();
    if(await page.locator('.workspace').getAttribute('data-right-collapsed')!=='true')throw Error('Inspector did not collapse');
    await page.locator('#right-restore').click();
    if(await page.locator('.workspace').getAttribute('data-right-collapsed')!=='false')throw Error('Inspector did not restore');
    const first=page.locator('#feature-tree [data-feature]').first();
    await first.click();
    const writesBeforeFocus=requests.length;
    await page.getByRole('button',{name:'Focus',exact:true}).click();
    if(requests.length!==writesBeforeFocus)throw Error('Focus sent an engineering request');
    await page.getByRole('button',{name:'Perspective',exact:true}).click();
    if(!await page.getByRole('button',{name:'Orthographic',exact:true}).count())throw Error('Projection did not change');
    await page.locator('#projects-open').click();
    if(!await page.locator('body').evaluate(node=>node.classList.contains('home')))throw Error('Projects Home did not open');
    await page.getByRole('button',{name:'Return to current draft'}).click();
    if(!await page.getByRole('button',{name:'Orthographic',exact:true}).count())throw Error('Home return lost projection state');
    const directions=await page.locator('.viewcube-menu [data-view]').evaluateAll(nodes=>nodes.map(node=>node.dataset.view));
    if(directions.length!==15)throw Error('Expected six faces, ISO and eight corners');
    for(const direction of directions){
      await page.getByRole('button',{name:'Open ViewCube directions'}).click();
      const option=page.locator(`.viewcube-menu [data-view="${direction}"]`);
      await option.click();
      if(await option.getAttribute('aria-current')!=='true')throw Error(`ViewCube direction ${direction} did not become active`);
    }
    await page.getByRole('button',{name:'Display',exact:true}).click();
    await page.locator('#clip-enabled').check();
    if((await page.locator('#viewport').getAttribute('data-clipping'))==='off')throw Error('Section plane did not activate');
    for(const axis of ['x','y','z']){
      await page.locator('#clip-axis').selectOption(axis);
      await page.locator('#clip-keep').selectOption('lte');
      await page.locator('#clip-position').fill('10');
      await page.locator('#clip-position').dispatchEvent('change');
      if((await page.locator('#viewport').getAttribute('data-clipping'))!==`${axis}:lte:10`)throw Error(`Section ${axis} did not apply`);
    }
    await page.locator('#clip-axis').selectOption('x');
    await page.locator('#clip-keep').selectOption('gte');
    await page.locator('#clip-position').fill('10');
    await page.locator('#clip-position').dispatchEvent('change');
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Isolate',exact:true}).click();
    if((await page.locator('#viewport').getAttribute('data-isolation'))!=='feature')throw Error('Feature isolation did not activate');
    await page.getByRole('button',{name:'Project actions'}).click();
    await page.locator('#json-open').click();
    if(!await page.locator('#json-dialog').isVisible())throw Error('Project JSON dialog did not open');
    await page.keyboard.press('Escape');
    if(await page.locator('#json-dialog').isVisible())throw Error('Native Escape did not close dialog');
    if((await page.locator('#viewport').getAttribute('data-isolation'))!=='feature'||(await page.locator('#viewport').getAttribute('data-clipping'))==='off')throw Error('Dialog Escape altered isolation or clipping');
    await page.waitForFunction(()=>document.activeElement?.id==='project-menu-trigger',undefined,{timeout:1000}).catch(()=>{});
    const returnedFocus=await page.evaluate(()=>document.activeElement?.id);
    if(returnedFocus!=='project-menu-trigger')throw Error('Dialog focus did not return to a visible trigger: '+returnedFocus);
    await page.keyboard.press('Escape');
    if((await page.locator('#viewport').getAttribute('data-isolation'))!=='none')throw Error('Second Escape did not clear isolation');
    await page.keyboard.press('Escape');
    if((await page.locator('#viewport').getAttribute('data-clipping'))!=='off')throw Error('Escape did not reset section after menu');
    await page.getByRole('button',{name:/Validation Results/}).click();
    if(!await page.locator('#validation-body').isVisible())throw Error('Validation drawer did not open');
    if(await page.locator('.locate-check').count())await page.locator('.locate-check').first().click();
    if(requests.length)throw Error('Read-only navigation sent a mutation request: '+requests.join(', '));
    await page.getByRole('button',{name:'Drawing',exact:true}).click();
    await page.locator('.drawing-workspace').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#project-title')?.textContent!=='Opening project…'&&document.querySelector('#message')?.textContent!=='Loading saved drawings');
    for(const [name,w,h] of [['drawing-1366x768',1366,768],['drawing-1920x1080',1920,1080],['drawing-1100x800',1100,800],['drawing-900x800',900,800]])await capture(name,w,h);
    if(savedDrawing){
      await page.setViewportSize({width:1366,height:768});
      await page.goto(savedDrawing);
      await page.locator('#paper-container svg').waitFor({state:'visible'});
      const paperFits=()=>page.waitForFunction(()=>{
        const paper=document.querySelector('#paper-container')?.getBoundingClientRect(),view=document.querySelector('#paper-viewport')?.getBoundingClientRect();
        return !!paper&&!!view&&paper.left>=view.left-2&&paper.right<=view.right+2&&paper.top>=view.top-2&&paper.bottom<=view.bottom+2;
      },undefined,{timeout:3000});
      await paperFits();
      await capture('drawing-saved-1366x768',1366,768);
      await page.setViewportSize({width:900,height:800});
      await page.getByRole('button',{name:'Fit sheet'}).click();
      await paperFits();
      await capture('drawing-saved-900x800',900,800);
    }
    if(requests.length)throw Error('Read-only Drawing navigation sent a mutation request: '+requests.join(', '));
    if(errors.length)throw Error(errors.join('\n'));
    return {passed:true,dimensions,blockedWrites:requests.length,blockedPreviewCancels:workerCancels.length,renderReads:renderReads.length,errors};
  }catch(error){
    await page.screenshot({path:`${output}/failure.png`});
    return {passed:false,error:String(error),dimensions,blockedWrites:requests,blockedPreviewCancels:workerCancels.length,renderReads:renderReads.length,errors};
  }
}
