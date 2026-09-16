import {build} from 'vite';
import {spawnSync} from 'node:child_process';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
await build({configFile:false,build:{outDir:'output/viewer-regression',emptyOutDir:false,
  lib:{entry:'tests/engineering-view.browser.js',name:'EngineeringView',formats:['iife'],fileName:'engineering-view'}}});
mkdirSync('output/playwright',{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){const r=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=engineering-view',...args],{env,encoding:'utf8'});process.stdout.write(r.stdout||'');process.stderr.write(r.stderr||'');if(r.status!==0||r.stdout?.includes('### Error'))throw Error('Engineering browser check failed: '+(r.error||r.status));}
cli('open','about:blank');
const root=process.cwd().replaceAll('\\','/');
try{
  for(const name of process.env.PMC_VIEW_FIXTURE?[process.env.PMC_VIEW_FIXTURE]:['A-same-net','B-conical','C-flat','D-plug','E-cross-net','F-source-port']){
    const fixture=JSON.parse(readFileSync(`output/v1-view-fixtures/${name}.json`,'utf8'));
    writeFileSync(`output/v1-view-fixtures/${name}.js`,'window.currentFixture='+JSON.stringify(fixture)+';');
    cli('run-code',`async page=>{
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto('about:blank');await page.setViewportSize({width:1100,height:760});
      await page.addStyleTag({path:${JSON.stringify(root+'/web/style.css')}});
      await page.addScriptTag({path:${JSON.stringify(root+'/output/viewer-regression/engineering-view.iife.js')}});
      await page.addScriptTag({path:${JSON.stringify(root+'/output/v1-view-fixtures/'+name+'.js')}});
      await page.evaluate(()=>window.setupEngineeringView(window.currentFixture));
      const results=[await page.evaluate(()=>window.assertStableStockTransition())];
      for(const mode of ['review','void','solid']){
        results.push(await page.evaluate(mode=>window.assertEngineeringView(mode),mode));
        await page.waitForTimeout(150);
        await page.screenshot({path:${JSON.stringify(root+'/output/playwright/'+name)}+'-'+mode+'.png'});
      }
      results.push(await page.evaluate(()=>window.assertEngineeringLayers()));
      if(await page.locator('.collision-notice').isVisible()){await page.getByRole('button',{name:'Isolate exact contact'}).click();await page.waitForTimeout(150);await page.screenshot({path:${JSON.stringify(root+'/output/playwright/'+name+'-collision.png')}});const kinds=await page.evaluate(()=>window.engineeringView.viewer.inspection().parts.filter(p=>p.visible).map(p=>p.kind));if(kinds.some(k=>k!=='collision')||!kinds.length)throw Error('Collision isolation failed');}
      if(${JSON.stringify(name)}==='B-conical'||${JSON.stringify(name)}==='C-flat'){await page.evaluate(()=>{window.engineeringView.viewer.mode('void');window.engineeringView.viewer.fit('front');});await page.waitForTimeout(150);await page.screenshot({path:${JSON.stringify(root+'/output/playwright/'+name+'-front.png')}});}
      results.push(await page.evaluate(()=>window.assertEngineeringPreview()));
      if(errors.length)throw Error(errors.join('\\n'));return results;
    }`);
  }
}finally{cli('close');}
writeFileSync('output/playwright/engineering-views-pass.json',JSON.stringify({passed:true,fixtures:6,modes:['hydraulic-net','machined-void','solid'],previewTips:[118,180]}));
