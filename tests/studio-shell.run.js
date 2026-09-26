async page => {
  const assert=(condition,message)=>{if(!condition)throw Error(message);};
  const apiWrites=[],pageErrors=[];
  page.on('request',request=>{
    if(request.method()==='POST'&&/\/api\/(?:projects(?:\/|$)|build$)/.test(request.url()))
      apiWrites.push(request.url());
  });
  page.on('pageerror',error=>pageErrors.push(error.message));
  page.on('dialog',dialog=>dialog.accept());
  const shot=async name=>page.screenshot({path:'output/playwright/'+name+'.png'});
  const geometry=()=>page.evaluate(()=>{
    const rect=id=>{const box=document.getElementById(id).getBoundingClientRect();return {width:box.width,height:box.height,left:box.left,top:box.top};};
    return {app:rect('app'),workspace:rect('viewport'),left:rect('select-block'),right:rect('right-toggle'),drawer:rect('validation-toggle'),statusHeight:document.querySelector('.status-strip').getBoundingClientRect().height,dirty:document.getElementById('dirty-dot').classList.contains('dirty'),scrollHeight:document.documentElement.scrollHeight};
  });
  await page.setViewportSize({width:1366,height:768});
  await page.goto('http://127.0.0.1:8765/');
  await page.getByRole('heading',{name:'Start a manifold'}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('#project-home')?.textContent.includes('Loading saved projects'));
  assert(!await page.locator('.validation-panel').isVisible(),'Home shows the validation drawer');
  await shot('studio-home-1366');
  await page.getByRole('button',{name:'New Manifold',exact:true}).click();
  await page.getByRole('dialog').getByRole('heading',{name:/New Manifold · 1 \/ 5/}).waitFor();
  await page.getByRole('dialog').getByRole('button',{name:'Next · Nets and ports'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Next · Cartridges and cavities'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Continue without cavities'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Next · Review'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Create editable draft'}).click();
  await page.locator('#viewport').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.getElementById('dirty-dot').classList.contains('dirty'));
  assert(await page.locator('svg.icon use[href^="#icon-"]').count()>=12,'Inline SVG command icons are missing');
  await page.locator('#reset-layout').click();
  const start=await geometry();
  assert(start.dirty,'Guided draft did not enter DRAFT state');
  assert(start.workspace.width>600&&start.workspace.height>500,'1366 workspace is too small');
  assert(start.statusHeight<=32,'Operation status strip is too tall');
  assert(start.scrollHeight<=769,'Studio scrolls the whole page at 1366×768');
  await page.locator('#projects-open').click();
  await page.getByRole('button',{name:'Return to current draft'}).waitFor();
  await page.getByRole('searchbox',{name:'Search saved projects'}).fill('No such saved UI QA project');
  await page.getByRole('button',{name:'Show archived projects'}).click();
  await page.getByRole('button',{name:'Show active projects'}).click();
  await page.getByRole('button',{name:'Return to current draft'}).click();
  assert((await geometry()).dirty,'Projects Home discarded the unsaved draft');
  const rules=page.locator('#inspector details.inspector-section').filter({has:page.locator('summary:text-is("Engineering rules")')});
  await rules.locator('summary').click();
  assert(!await rules.evaluate(node=>node.open),'Inspector section did not collapse');
  await page.locator('#feature-tree .tree-feature').first().click();
  await page.locator('#select-block').click();
  assert(!await rules.evaluate(node=>node.open),'Inspector section state did not survive selection changes');
  await page.locator('#project-menu-trigger').click();
  assert(await page.locator('#project-new').isVisible(),'Project commands are missing');
  await page.locator('#project-menu-trigger').press('Escape');
  assert(await page.locator('#project-menu-trigger').getAttribute('aria-expanded')==='false','Escape did not close the project menu');
  await page.locator('#project-menu-trigger').press('ArrowDown');
  assert(await page.evaluate(()=>document.activeElement?.id==='project-new'),'Keyboard menu did not focus its first command');
  await page.locator('#project-new').press('Escape');
  assert(await page.evaluate(()=>document.activeElement?.id==='project-menu-trigger'),'Closing a menu did not restore trigger focus');
  await page.locator('#engineering-menu-trigger').click();
  await page.locator('#library-open').click();
  await page.getByRole('dialog').getByRole('heading',{name:'Engineering Library · SQLite'}).waitFor();
  await page.locator('#workflow-close').click();
  await page.locator('#add-feature-trigger').click();
  await page.locator('#add-cavity').click();
  await page.getByRole('dialog').getByRole('heading',{name:'Engineering Library · SQLite'}).waitFor();
  await page.locator('#workflow-close').click();
  for(const [id,title] of [
    ['add-port','Add external port'],
    ['add-mounting','Add mounting hole'],
    ['add-engraving','Add production engraving'],
    ['add-block-modifier','Add limited block machining'],
  ]){
    await page.locator('#add-feature-trigger').click();
    await page.locator('#'+id).click();
    await page.getByRole('dialog').getByRole('heading',{name:title}).waitFor();
    await page.locator('#workflow-close').click();
  }
  await page.locator('#display-menu-trigger').click();
  assert(await page.locator('#opacity').isVisible(),'Stock opacity is absent from Display');
  assert(await page.locator('#circuits .circuit-toggle').count()===4,'Per-net visibility was lost');
  await page.locator('#display-menu-trigger').click();
  await page.locator('#compact-mode').selectOption('solid');
  assert(await page.locator('#solid-mode').getAttribute('class')==='active','Compact mode did not call the original Solid handler');
  await shot('studio-draft-1366');

  const splitter=await page.locator('#left-split').boundingBox();
  await page.mouse.move(splitter.x+splitter.width/2,splitter.y+100);
  await page.mouse.down();
  await page.mouse.move(splitter.x+splitter.width/2+30,splitter.y+100);
  await page.mouse.up();
  const resized=await geometry();
  assert(resized.workspace.width<start.workspace.width-20,'Panel resize did not allocate width to the Feature Tree');
  assert(resized.dirty,'Layout resize changed draft state');
  assert((await page.evaluate(()=>JSON.parse(localStorage.getItem('pmc:studio-layout:v1')))).left>=280,'Panel width was not stored locally');
  const widthAfterDrag=(await page.evaluate(()=>JSON.parse(localStorage.getItem('pmc:studio-layout:v1')))).left;
  await page.locator('#left-split').press('ArrowRight');
  assert((await page.evaluate(()=>JSON.parse(localStorage.getItem('pmc:studio-layout:v1')))).left===widthAfterDrag+10,'Keyboard splitter adjustment failed');
  await page.locator('#left-toggle').click();
  assert((await geometry()).workspace.width>resized.workspace.width+200,'Collapsing the tree did not enlarge the viewport');
  await page.locator('#left-restore').click();
  await page.locator('#right-toggle').click();
  assert(await page.locator('#right-restore').isVisible(),'Inspector restore control is missing');
  await page.locator('#right-restore').click();
  await page.locator('#validation-toggle').click();
  await page.locator('#notice-expand').click();
  assert(await page.locator('#notice-expand').getAttribute('aria-expanded')==='true','Status detail did not expand');
  await page.locator('#notice-expand').click();
  assert(await page.locator('#validation-body').isVisible(),'Validation drawer did not open');
  assert((await geometry()).workspace.height<start.workspace.height-100,'Validation drawer did not reduce viewport height');
  await shot('studio-validation-1366');
  await page.locator('#validation-toggle').click();

  await page.setViewportSize({width:1920,height:1080});
  assert(await page.locator('#review-mode').isVisible(),'Wide HUD modes are missing');
  await shot('studio-draft-1920');
  await page.setViewportSize({width:2560,height:1440});
  await shot('studio-draft-2560');
  await page.setViewportSize({width:1100,height:800});
  assert(!await page.locator('.right-panel').isVisible(),'Inspector should default to overlay at 1100px');
  await page.locator('#right-restore').click();
  assert(await page.locator('.right-panel').isVisible(),'Inspector overlay did not open');
  await shot('studio-inspector-1100');
  await page.locator('#right-toggle').click();
  await page.setViewportSize({width:900,height:800});
  assert(!await page.locator('.left-panel').isVisible(),'Feature Tree should default to overlay below 1024px');
  await page.locator('#left-restore').click();
  assert(await page.locator('.left-panel').isVisible(),'Feature Tree overlay did not open');
  await page.locator('#right-restore').click();
  assert(!await page.locator('.left-panel').isVisible()&&await page.locator('.right-panel').isVisible(),'Narrow overlays did not stay mutually exclusive');
  await shot('studio-inspector-900');
  assert((await geometry()).dirty,'Responsive changes modified draft state');
  assert(!apiWrites.length,'UI-only interactions wrote a project or started a build: '+apiWrites.join(', '));
  assert(!pageErrors.length,'Page error: '+pageErrors.join(' | '));
  return {screenshots:7,apiWrites,pageErrors};
}
