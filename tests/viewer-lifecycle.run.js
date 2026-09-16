async (page) => {
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  await page.setViewportSize({width:1100,height:900});
  await page.goto('about:blank');
  await page.addScriptTag({path:'__PROJECT_ROOT__/output/viewer-regression/viewer-regression.iife.js'});
  const points=await page.evaluate(()=>window.setupViewerLifecycle());
  await page.waitForTimeout(250);
  await page.mouse.move(points.start.x,points.start.y);await page.mouse.down();
  let released=false;try {
    for(const point of points.moves){await page.mouse.move(point.x,point.y);await page.waitForTimeout(30);}
    await page.mouse.up();released=true;await page.waitForTimeout(50);
    const result=await page.evaluate(()=>window.assertViewerLifecycle());
    if(errors.length)throw Error(errors.join('\n'));
    await page.screenshot({path:'__PROJECT_ROOT__/output/playwright/v8-continuous-drag-final.png'});
    return result;
  } finally {if(!released)await page.mouse.up();}
}
