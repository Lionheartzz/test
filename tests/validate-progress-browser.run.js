async page => {
  const base='__BASE_URL__',output='__OUTPUT_DIR__',projectId='__PROJECT_ID__';
  const errors=[],runs=[];let current=null;
  const assert=(value,message)=>{if(!value)throw Error(message);};
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{
    if(current&&request.url()===base+'/api/build'){
      const payload=request.postDataJSON();current.requests++;
      assert(payload.project_id===projectId,'Wrong project submitted');current.operationId=payload.operation_id;
    }
  });
  page.on('response',async response=>{
    if(!current)return;const run=current;
    if(response.url().startsWith(base+'/api/engineering/progress/')&&response.ok()){
      const status=await response.json();if(status.operation_id===run.operationId){run.finalStatus=status;run.statuses.push({elapsed_s:status.elapsed_s,percent:status.percent,stage:status.stage,candidate:status.candidate,state:status.state});}
    }
    if(response.url()===base+'/api/build'){const result=await response.json();run.response={operation_id:result.operation_id,build:result.build};run.responseAt=Date.now();}
  });
  try{
    await page.setViewportSize({width:1580,height:1040});await page.goto(base);
    await page.locator(`[data-project-id="${projectId}"]`).getByRole('button',{name:'Open CAD',exact:true}).click();
    await page.getByLabel('Engineering material',{exact:true}).waitFor();
    assert(await page.locator('#validate-progress').isHidden(),'Preview showed Validate progress');
    for(let index=0;index<3;index++){
      const run={index:index+1,requests:0,statuses:[],samples:[],screenshots:[],started:Date.now()};current=run;
      await page.getByRole('button',{name:'Validate',exact:true}).click();
      await page.locator('#validate-progress').waitFor({state:'visible'});
      assert(await page.locator('#build').isDisabled(),'Duplicate Validate not disabled');
      await page.locator('#build').dispatchEvent('click');
      let previous=0;
      while(Date.now()-run.started<330000){
        const sample=await page.locator('#validate-progress').evaluate(root=>({visible:!root.hidden,
          percent:root.querySelector('progress').value,stage:root.querySelector('[data-validate-stage]').textContent,
          detail:root.querySelector('[data-validate-candidate]').textContent,time:root.querySelector('[data-validate-time]').textContent,
          recent:root.querySelector('[data-validate-recent]').textContent}));
        if(sample.visible){
          assert(sample.percent>=previous,'Progress decreased');previous=sample.percent;
          assert(!/operation\.build|route\.resolution|boolean\./.test(sample.stage),'Raw phase exposed');
          if(sample.percent===100)assert(run.response?.operation_id===run.operationId,'100% before authoritative response');
          const last=run.samples.at(-1);if(!last||Object.keys(sample).some(key=>sample[key]!==last[key]))run.samples.push({...sample,t:Date.now()-run.started});
          const label=sample.stage.includes('STEP')?'step':sample.detail.includes('candidate 2')?'candidate-2':sample.detail.includes('candidate 1')?'candidate-1':'preparing';
          if(!run.screenshots.includes(label)){await page.screenshot({path:output+`/run-${index+1}-${label}.png`});run.screenshots.push(label);}
        }
        if(run.response&&!(await page.locator('#build').isDisabled())&&await page.locator('#validate-progress').isHidden())break;
        await page.waitForTimeout(75);
      }
      assert(run.requests===1,'Duplicate build submitted');assert(run.response?.build?.counts?.FAIL===0,'Real CAD-safe result failed');
      assert(run.samples.some(s=>s.percent===100),'Completion never shown');
      assert(run.samples.some(s=>s.detail.includes('candidate 1'))&&run.samples.some(s=>s.detail.includes('candidate 2')),'Candidates not visible');
      const final=run.finalStatus;assert(final.state==='complete','Owned progress did not complete');
      run.elapsed=final.elapsed_s;
      run.stageSequence=final.events.map(e=>e.stage_text+(e.candidate?' · candidate '+e.candidate:''));
      assert(final.events.some(e=>e.stage==='alternate')&&final.events.some(e=>e.stage==='step'),'Fallback / STEP milestones missing');
      run.etaSeen=run.samples.some(s=>/about \d+ s remaining/.test(s.time));
      if(index===0)assert(!run.etaSeen,'First run invented an ETA');
      if(index===2)assert(run.etaSeen,'Matching history did not produce ETA');
      assert((await page.locator('#check-counts').innerText()).includes('450 PASS / 12 WARNING / 0 FAIL'),'Final results changed');
      await page.screenshot({path:output+`/run-${index+1}-complete.png`});runs.push(run);
    }
    current=null;
    await page.route(base+'/api/build',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Browser QA transport failure'})}));
    await page.getByRole('button',{name:'Validate',exact:true}).click();
    await page.getByText('Browser QA transport failure',{exact:true}).waitFor();
    assert(!(await page.locator('#build').isDisabled()),'Error kept Validate disabled');
    assert(await page.locator('#validate-progress').isHidden(),'Error left progress visible');
    await page.unroute(base+'/api/build');
    assert(errors.length===0,'Page errors: '+errors.join('; '));
    return {passed:true,base,runs,errors,errorRestored:true};
  }catch(error){await page.screenshot({path:output+'/failure.png'});return {passed:false,error:error.message,runs,current,errors};}
}
