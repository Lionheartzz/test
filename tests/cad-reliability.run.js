async page=>{
  const root='__PROJECT_ROOT__',errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.setViewportSize({width:1440,height:1000});
  const edit=async value=>{const field=page.getByRole('spinbutton',{name:'Length X / mm',exact:true});await field.fill(String(value));await field.press('Tab');};
  const ready=()=>page.waitForFunction(()=>document.querySelector('#model-info').textContent.includes('NOT OPTIMIZED')&&document.querySelector('.viewport-loading').hidden,{},{timeout:25000});
  await edit(Number(await page.getByRole('spinbutton',{name:'Length X / mm',exact:true}).inputValue())+.25);
  await ready();
  await page.getByRole('combobox',{name:'View face',exact:true}).selectOption('front');
  await page.getByRole('slider',{name:'Stock opacity',exact:true}).evaluate(e=>{e.value='37';e.dispatchEvent(new Event('input',{bubbles:true}));});
  const state=()=>page.locator('#viewport').evaluate(e=>({mode:e.dataset.viewMode,stock:e.dataset.stockVisible,opacity:e.dataset.stockOpacity}));
  const before=await state();
  let held,release;
  await page.route('**/api/preview-solid',async route=>{
    held=true;await new Promise(resolve=>release=resolve);
    await route.abort().catch(()=>{});
  });
  await edit(121);
  await page.waitForFunction(()=>document.querySelector('.viewport-loading').textContent.includes('Computing exact')&&!document.querySelector('.viewport-loading').hidden);
  await page.waitForFunction(()=>document.querySelector('#model-info').textContent.includes('PREVIEW FAILED'),{},{timeout:25000});
  const failure=await page.locator('#model-info').innerText();
  if(!held||!failure.includes('interactive time limit')||!failure.includes('LAST USABLE VIEW RETAINED'))throw Error(failure);
  if(!await page.locator('.viewport-loading').isHidden())throw Error('Computing state stuck after timeout');
  if(!await page.getByRole('button',{name:'Save Project',exact:true}).isEnabled())throw Error('Preview disabled project saving');
  if(JSON.stringify(before)!==JSON.stringify(await state()))throw Error('Mode or stock context changed on failure');
  await page.screenshot({path:root+'/output/playwright/cad-timeout-retained.png',fullPage:true});
  release();await page.unroute('**/api/preview-solid');
  await edit(122);await edit(123);await edit(124);await ready();
  if(JSON.stringify(before)!==JSON.stringify(await state()))throw Error('Exact replacement changed mode/context');
  if(await page.getByRole('combobox',{name:'View face',exact:true}).inputValue()!=='front')throw Error('View direction changed');
  await page.getByRole('button',{name:'Save & Validate',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='PASS'&&!document.body.classList.contains('busy'),{},{timeout:30000});
  if(!await page.locator('.viewport-loading').isHidden())throw Error('Computing state remained after build');
  if(JSON.stringify(before)!==JSON.stringify(await state()))throw Error('Build replacement changed mode/context');
  if(!await page.getByRole('button',{name:'Save Project',exact:true}).isEnabled())throw Error('Saving not reenabled');
  await page.screenshot({path:root+'/output/playwright/cad-recovered-build.png',fullPage:true});
  if(errors.length)throw Error(errors.join('\n'));
  return {passed:true,timeout:failure,retainedContext:before,recoveredBuild:'PASS',pageErrors:errors};
}
