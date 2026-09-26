async page=>{
  const root='__PROJECT_ROOT__';
  const design=__DESIGN__;
  design.name='Preview follow-up QA '+Date.now();
  const created=await page.request.post('http://127.0.0.1:8765/api/projects',{headers:{'X-PMC-Request':'local-console'},data:{design}});
  if(!created.ok())throw Error(await created.text());
  const calls=[];let held=false,release;
  await page.route('**/api/preview',async route=>{
    const snapshot=route.request().postDataJSON();calls.push({type:'fast',length:snapshot.block.length});
    if(held){held=false;await new Promise(r=>release=r);await route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:'obsolete route snapshot'})});}
    else await route.continue();
  });
  page.on('request',r=>{if(r.url().endsWith('/api/preview-solid'))calls.push({type:'exact',length:r.postDataJSON().block.length});});
  await page.goto('http://127.0.0.1:8765');await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('searchbox',{name:'Search saved projects'}).fill(design.name);
  await page.locator('[data-project-id]').filter({hasText:design.name}).getByRole('button',{name:'Open CAD',exact:true}).click();
  const ready=()=>page.waitForFunction(()=>document.querySelector('#model-info').textContent.includes('NOT OPTIMIZED')&&document.querySelector('.viewport-loading').hidden);
  await ready();calls.length=0;
  const edit=async value=>{await page.getByRole('spinbutton',{name:'Length X / mm',exact:true}).fill(String(value));await page.getByRole('spinbutton',{name:'Length X / mm',exact:true}).press('Tab');};
  for(const value of [101,102,103])await edit(value);
  await ready();
  if(JSON.stringify(calls)!==JSON.stringify([{type:'fast',length:103},{type:'exact',length:103}]))throw Error('Burst not coalesced: '+JSON.stringify(calls));
  calls.length=0;held=true;await edit(104);
  while(!release)await page.waitForTimeout(10);
  await edit(105);await edit(106);await page.waitForTimeout(400);
  if(calls.length!==1)throw Error('Concurrent obsolete requests');release();await ready();
  if(calls.some(c=>c.type==='exact'&&c.length!==106)||await page.locator('#notice').innerText()==='Preview: obsolete route snapshot')throw Error('Obsolete result leaked');
  await edit(0);
  await page.waitForFunction(()=>document.querySelector('#model-info').textContent.includes('PREVIEW FAILED'));
  const failure=await page.locator('#model-info').innerText();
  if(!failure.includes('block.length')||!(await page.locator('.viewport-loading').isHidden()))throw Error('422 reason or loading cleanup missing: '+failure);
  await page.screenshot({path:root+'/output/playwright/preview-followup-422.png',fullPage:true});
  await edit(107);await ready();
  const stock=page.getByRole('slider',{name:'Stock opacity',exact:true});
  await stock.evaluate(e=>{e.value='37';e.dispatchEvent(new Event('input',{bubbles:true}));});
  if(await page.locator('#viewport').getAttribute('data-stock-opacity')!=='0.37'||await page.locator('#viewport').getAttribute('data-stock-visible')!=='true')throw Error('Stock opacity not applied');
  await page.screenshot({path:root+'/output/playwright/preview-followup-context.png',fullPage:true});
  await stock.evaluate(e=>{e.value='0';e.dispatchEvent(new Event('input',{bubbles:true}));});
  if(await page.locator('#viewport').getAttribute('data-stock-visible')!=='false')throw Error('Zero opacity still shows stock');
  await page.getByRole('button',{name:'Solid',exact:true}).click();
  if(await page.locator('#viewport').getAttribute('data-stock-opacity')!=='1')throw Error('Solid not opaque');
  await page.getByRole('button',{name:'Hydraulic nets',exact:true}).click();
  if(await page.locator('#viewport').getAttribute('data-stock-visible')!=='false')throw Error('Mode change lost opacity preference');
  const result={passed:true,burstRequests:2,serialized:true,failure,recovered:true,stockContext:true};
  return result;
}
