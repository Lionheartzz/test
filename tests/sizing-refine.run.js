async page=>{
  const root='__PROJECT_ROOT__',headers={'X-PMC-Request':'local-console'};
  const design={name:'Sizing refine QA '+Date.now(),block:{length:120,width:100,height:100,material:'QA'},features:[['P1','left'],['P2','right']].map(([id,face])=>({id,kind:'port',face,u:50,v:50,circuit:'P',diameter:20,depth:20,tip_angle:180})),nets:[{id:'P',members:['P1','P2'],routing:'automatic',flow_lpm:40,velocity_limit:6}]};
  const created=await page.request.post('http://127.0.0.1:8765/api/projects',{headers,data:{design}});
  if(!created.ok())throw Error(await created.text());
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765');await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('searchbox',{name:'Search saved projects'}).fill(design.name);
  await page.locator('[data-project-id]').filter({hasText:design.name}).getByRole('button',{name:'Open CAD',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#model-info').textContent.includes('NOT OPTIMIZED'));
  await page.locator('#nets-open').click();
  if(!await page.getByText('Flow sized: requires', {exact:false}).isVisible())throw Error('Sizing status missing');
  if(await page.getByRole('spinbutton',{name:'Drill diameter · P',exact:true}).inputValue()!=='12')throw Error('Selected diameter not shown');
  await page.screenshot({path:root+'/output/playwright/sizing-status.png',fullPage:true});
  await page.locator('#workflow-dialog').evaluate(e=>e.close());
  const segment=page.locator('#feature-tree [data-feature^="R-"]').first();
  const id=await segment.getAttribute('data-feature');await segment.click();
  const stock=page.getByRole('slider',{name:'Stock opacity',exact:true});
  await stock.evaluate(e=>{e.value='37';e.dispatchEvent(new Event('input',{bubbles:true}));});
  let release,requestBody,adopted,fail=true;
  await page.route('**/api/freeze-net',async route=>{
    if(fail){fail=false;await route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:'Displayed proposal is stale: refresh before refining.'})});return;}
    requestBody=route.request().postDataJSON();await new Promise(r=>release=r);
    const response=await route.fetch();adopted=await response.json();await route.fulfill({response});
  });
  await page.getByRole('button',{name:'Refine in 3D',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('Refine failed: Displayed proposal is stale'));
  if(!await page.locator('.viewport-loading').isHidden())throw Error('Failed adoption left a waiting state');
  await page.getByRole('button',{name:'Refine in 3D',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('Adopting displayed route'));
  if(!await page.getByRole('button',{name:'Refine in 3D',exact:true}).isDisabled())throw Error('Adoption button has no pending state');
  if(!release)throw Error('No adoption request');release();
  await page.waitForFunction(()=>document.querySelector('#inspector').textContent.includes('Refined route'));
  const signature=f=>JSON.stringify([f.id,f.face,f.u,f.v,f.depth,f.diameter,f.direction,f.plugged]);
  const before=requestBody.proposal.features.filter(f=>f.route_net==='P').map(signature);
  const after=adopted.features.filter(f=>f.frozen_net==='P').map(signature);
  if(JSON.stringify(before)!==JSON.stringify(after)||adopted.features.some(f=>f.route_net==='P'))throw Error('Displayed geometry/ownership changed');
  if(await page.locator('#feature-tree .active').getAttribute('data-feature')!==id)throw Error('Selection lost');
  if(await page.locator('#viewport').getAttribute('data-geometry')!=='machined-brep'||await page.locator('#viewport').getAttribute('data-stock-opacity')!=='0.37')throw Error('Exact geometry or visibility jumped');
  await page.screenshot({path:root+'/output/playwright/refine-adopted.png',fullPage:true});
  // Find the selected bore's actual hit area, then drag it through the real pointer path.
  const canvas=page.locator('#viewport canvas'),box=await canvas.boundingBox();let hit;
  for(let y=box.y+box.height*.3;y<box.y+box.height*.75&&!hit;y+=15){
    for(let x=box.x+box.width*.2;x<box.x+box.width*.8;x+=15){
      await page.mouse.move(x,y);
      if(await page.locator('#viewport').getAttribute('data-hovered-feature')===id){hit={x,y};break;}
    }
  }
  if(!hit)throw Error('Frozen segment has no draggable hit area');
  const u=await page.getByRole('spinbutton',{name:'Position U / mm',exact:true}).inputValue();
  const v=await page.getByRole('spinbutton',{name:'Position V / mm',exact:true}).inputValue();
  await page.mouse.move(hit.x,hit.y);await page.mouse.down();await page.mouse.move(hit.x+35,hit.y+25,{steps:4});await page.mouse.up();
  await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('Draft exact checks'));
  if(u===await page.getByRole('spinbutton',{name:'Position U / mm',exact:true}).inputValue()&&v===await page.getByRole('spinbutton',{name:'Position V / mm',exact:true}).inputValue())throw Error('Dragging did not edit segment');
  if(errors.length)throw Error(errors.join('\n'));
  return {passed:true,diameter:12,visibleGeometryPreserved:true,selectionPreserved:true,dragged:true};
}
