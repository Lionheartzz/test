async page => {
  const base='__BASE_URL__',output='__OUTPUT_DIR__',dialog=page.locator('#workflow-dialog'),errors=[],headers={'X-PMC-Request':'local-console'},assert=(v,m)=>{if(!v)throw Error(m);};
  page.on('pageerror',e=>errors.push(e.message));const json=async r=>{assert(r.ok(),await r.text());return r.json();};const api=p=>page.request.get(base+p).then(json);
  const management=async()=>{await page.getByRole('button',{name:'AI Design',exact:true}).click();await dialog.getByRole('heading',{name:'AI Design · Management',exact:true}).waitFor();};
  const close=async()=>{await dialog.press('Escape');await dialog.waitFor({state:'hidden'});};
  try{
    assert((await api('/api/health')).network.qa_isolated,'Isolated QA only');await page.setViewportSize({width:1580,height:1040});await page.goto(base);
    await management();const real=dialog.locator('.library-card').filter({has:page.getByRole('heading',{name:'test',exact:true})});
    await real.getByRole('button',{name:'Open',exact:true}).waitFor();assert((await real.innerText()).includes('Screenshot 2026-09-11 142739.png'),'Missing document summary');
    assert((await real.innerText()).includes('Analysis: Completed'),'Completed provider mislabeled');assert((await real.innerText()).includes('Generated drafts: 0'),'Missing draft count');
    await page.screenshot({path:output+'/management.png'});await real.getByRole('button',{name:'Open',exact:true}).click();
    await dialog.getByLabel('Analysis title',{exact:true}).waitFor();await dialog.getByRole('button',{name:'Create manifold draft',exact:true}).click();
    await dialog.getByRole('heading',{name:'Draft generation needs 2 decisions',exact:true}).waitFor({timeout:60000});
    assert((await dialog.innerText()).includes('no runtime cartridge matches'),'Wrong identity diagnostic');assert((await dialog.innerText()).includes('crack pressure: 280'),'Lost pressure recognition');
    assert(await dialog.getByRole('heading',{name:'G1/4 BSPP external port definition',exact:true}).count()===1,'Duplicate BSPP decisions');
    assert((await dialog.innerText()).includes('Applies to: P, A'),'Missing shared application');await page.screenshot({path:output+'/rdha-resolution.png'});
    await close();await management();assert((await real.innerText()).includes('Analysis: Completed'),'Binding failure became analysis failure');assert((await real.innerText()).includes('Needs 2 engineering decisions'),'Generation status absent');
    await real.getByRole('button',{name:'Open',exact:true}).click();await dialog.getByLabel('Analysis title',{exact:true}).fill('Dirty preserved title');await dialog.getByLabel('Analysis title',{exact:true}).press('Tab');
    await close();await management();const unsaved=dialog.locator('.library-card').filter({has:page.getByRole('heading',{name:'Unsaved AI Design',exact:true})});
    await unsaved.getByRole('button',{name:'Resume',exact:true}).click();assert(await dialog.getByLabel('Analysis title',{exact:true}).inputValue()==='Dirty preserved title','Dirty input lost');
    await dialog.getByRole('button',{name:'Back to AI Design Management',exact:true}).click();await dialog.getByRole('heading',{name:'AI Design · Management',exact:true}).waitFor();
    await dialog.getByRole('button',{name:'New AI Design',exact:true}).click();await dialog.getByLabel('Analysis title',{exact:true}).fill('QA delete workspace');await dialog.getByLabel('Analysis title',{exact:true}).press('Tab');
    await dialog.getByLabel('Upload schematic documents',{exact:true}).setInputFiles('D:/Project/Manifold/tests/fixtures/ai-demo.png');
    await dialog.getByText('ai-demo.png',{exact:true}).waitFor();await dialog.getByLabel('Analysis provider',{exact:true}).selectOption('qa-slow');
    await dialog.getByRole('button',{name:'Start analysis',exact:true}).click();await dialog.getByText(/You may close this dialog and return later/).waitFor();
    await close();await management();let running=dialog.locator('.library-card').filter({has:page.getByRole('heading',{name:'QA delete workspace',exact:true})});await running.getByText('Analysis: Running',{exact:true}).waitFor();assert(await running.getByRole('button',{name:'Delete',exact:true}).isDisabled(),'Running Delete enabled');
    const rows=await api('/api/ai-design/tasks'),created=rows.find(r=>r.title==='QA delete workspace');
    assert((await page.request.delete(base+'/api/ai-design/tasks/'+created.id,{headers:{...headers,'Content-Type':'application/json'}})).status()===409,'Running deletion accepted');
    await running.getByText('Analysis: Completed',{exact:true}).waitFor({timeout:20000});assert(await dialog.getByRole('heading',{name:'AI Design · Management',exact:true}).isVisible(),'Job completion hijacked Management');
    const project=await json(await page.request.post(base+'/api/projects',{headers,data:{design:{schema_version:3,name:'QA project remains',block:{length:80,width:80,height:80,material:'QA'}}}}));
    const stored=await api('/api/ai-design/tasks/'+created.id),asset=stored.inputs.documents[0].asset;
    const beforeProject=await api('/api/projects/'+project.project_id),beforeReal=await api('/api/ai-design/tasks/5c6769d0d15c4c78a81cd0fd4ef83217');
    page.once('dialog',d=>d.accept());await running.getByRole('button',{name:'Delete',exact:true}).click();await dialog.getByRole('heading',{name:'QA delete workspace',exact:true}).waitFor({state:'hidden'});
    assert((await api('/api/projects/'+project.project_id)).revision===beforeProject.revision,'Saved project changed');assert((await api('/api/ai-design/tasks/5c6769d0d15c4c78a81cd0fd4ef83217')).revision===beforeReal.revision,'Other workspace changed');
    assert((await page.request.get(base+'/api/assets/'+asset.sha256)).ok(),'Shared asset removed');assert(errors.length===0,errors.join('; '));
    const result={passed:true,sourceWorkspace:'5c6769d0d15c4c78a81cd0fd4ef83217',decisionsBefore:3,decisionsAfter:2,sharedBSPPDecision:true,dirtyResumed:true,runningDeletionBlocked:true,completedJobKeptManagement:true,deletePreservesProjectAssetAndOtherTask:true,errors};
    await page.evaluate(result=>window.__aiManagementQA=result,result);return result;
  }catch(e){await page.screenshot({path:output+'/failure.png'});return {passed:false,error:e.message,errors};}
}
