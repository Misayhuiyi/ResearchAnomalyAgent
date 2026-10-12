/* Explicit mode: mock = free isolated software flow; live requires bounded approval. */
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.env.PAPER_CORPUS_RESULTS||'');
const mode=process.env.PAPER_CORPUS_AI_MODE,base=process.env.DEMO_URL;
if(!out.startsWith(path.join(root,'test-results')+path.sep))throw Error('Isolated output required');
if(!['mock','live'].includes(mode)||new URL(base).hostname!=='127.0.0.1')throw Error('Explicit test mode/loopback required');
const records=JSON.parse(fs.readFileSync(path.join(out,'browser-summary.json'))).cases;
const failureOnly=process.env.PAPER_CORPUS_AI_FAILURE_ONLY==='1';
if(failureOnly&&mode!=='mock')throw Error('Failure-only mode is for free mock tests');
const targets=failureOnly?[]:records.filter(r=>r.workflow_passed&&r.selected_finding);
if(mode==='mock'&&new URL(base).port!=='8896')throw Error('Use mock server only');
const approved=Number(process.env.PAPER_CORPUS_APPROVED_MICROS||0);
if(mode==='live'&&(process.env.PAPER_CORPUS_LIVE_APPROVAL!=='USER_CONFIRMED'||approved<=0))throw Error('New explicit user fee approval required');
const check=(v,m)=>{if(!v)throw Error(m)},sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const result=[];let reserved=0,calls=0;
(async()=>{const browser=await chromium.launch({headless:true});
 try{
  for(const r of targets){const page=await browser.newPage(),errors=[],at=new Date().toISOString();page.on('pageerror',e=>errors.push(e.message));
   const record={case_id:r.case_id,scan_id:r.scan_id,finding_id:r.selected_finding,mode,at,passed:false};
   try{
    await page.goto(base,{waitUntil:'networkidle'});await page.evaluate(id=>openJob(id),r.scan_id);
    await page.waitForSelector('#resultView:not(.hidden)');await page.locator(`[data-finding="${r.selected_finding}"]`).click();
    const before=await page.request.get(new URL(`/artifact/${r.scan_id}/result.json`,base).href),digest=sha(await before.body());
    await page.waitForFunction(()=>!document.getElementById('aiStatus').textContent.includes('正在读取'));
    await page.click('#aiQuoteBtn');await page.waitForSelector('#aiConfirmBtn:not(.hidden)');
    const quote=(await (await page.request.get(new URL(`/api/explanations/${r.scan_id}/${r.selected_finding}`,base).href)).json()).ai;
    record.quote_max_micros=quote.estimated_max_micros;
    if(mode==='live'){check(calls<12,'Call-count cap exceeded');check(reserved+quote.estimated_max_micros<=approved,'Cumulative authorized cap exceeded');reserved+=quote.estimated_max_micros;}
    calls++;record.provider_request_attempted=mode==='live';
    await page.click('#aiConfirmBtn');
    await page.waitForFunction(()=>!document.getElementById('aiConfirmBtn').disabled,{},{timeout:90000});
    const state=(await (await page.request.get(new URL(`/api/explanations/${r.scan_id}/${r.selected_finding}`,base).href)).json()).ai;
    record.state=state;check(state.status==='completed',state.message||'Explanation did not complete');
    check(await page.locator('#aiOutput:not(.hidden)').count()===1,'Explanation is not visible');
    check((await page.innerText('#aiBoundary')).includes('不代表科研不端结论'),'Boundary missing');
    const explanation=state.explanation;check(['what','why','report_summary'].every(k=>typeof explanation[k]==='string'&&explanation[k].length>0),'Text fields missing');
    check(['benign_explanations','check_steps'].every(k=>Array.isArray(explanation[k])&&explanation[k].length>0),'Lists missing');
    check(state.source_hash&&state.evidence_hash,'Traceability absent');
    if(mode==='mock')check(explanation.what.includes('【模拟响应】'),'Mock not explicitly marked');
    await page.reload({waitUntil:'networkidle'});await page.evaluate(id=>openJob(id),r.scan_id);
    await page.waitForSelector('#resultView:not(.hidden)');await page.locator(`[data-finding="${r.selected_finding}"]`).click();
    await page.waitForSelector('#aiOutput:not(.hidden)');check(await page.innerText('#aiWhat')===explanation.what,'Reload changed explanation');
    const after=await page.request.get(new URL(`/artifact/${r.scan_id}/result.json`,base).href);
    check(sha(await after.body())===digest,'AI changed deterministic result');check(!errors.length,errors.join('; '));
    record.passed=true;
    await page.screenshot({path:path.join(out,r.case_id,`${mode}-ai.png`)});
   }catch(e){record.error=e.message;record.passed=false;}
   finally{result.push(record);fs.writeFileSync(path.join(out,`${mode}-ai-summary.json`),JSON.stringify({mode,at:new Date().toISOString(),
      configured_model:'deepseek-flash',provider_calls:mode==='live'?calls:0,mock_attempts:mode==='mock'?calls:0,
      authorized_max_micros:mode==='live'?approved:0,reserved_max_micros:reserved,records:result,passed:result.filter(x=>x.passed).length,failed:result.filter(x=>!x.passed).length,
      quality_scope:'schema, binding, persistence and boundary; human interpretation quality remains pending'},null,2));
    console.log(JSON.stringify({mode,case:r.case_id,passed:record.passed,error:record.error||null}));await page.close();}
  }
  if(mode==='mock'){
   const failure=JSON.parse(fs.readFileSync(path.join(out,'mock-failure-target.json'))),page=await browser.newPage();
   await page.goto(base);await page.evaluate(id=>openJob(id),failure.scan_id);await page.waitForSelector('#resultView:not(.hidden)');
   await page.locator(`[data-finding="${failure.finding_id}"]`).click();await page.waitForFunction(()=>!document.getElementById('aiStatus').textContent.includes('正在读取'));
   const before=await page.request.get(new URL(`/artifact/${failure.scan_id}/result.json`,base).href),digest=sha(await before.body());
   const existing=(await (await page.request.get(new URL(`/api/explanations/${failure.scan_id}/${failure.finding_id}`,base).href)).json()).ai;
   if(existing.status!=='failed'){
    await page.click('#aiQuoteBtn');await page.waitForSelector('#aiConfirmBtn:not(.hidden)');await page.click('#aiConfirmBtn');
    await page.waitForFunction(()=>!document.getElementById('aiConfirmBtn').disabled,{},{timeout:30000});
   }
   const failedState=(await (await page.request.get(new URL(`/api/explanations/${failure.scan_id}/${failure.finding_id}`,base).href)).json()).ai;
   check(failedState.status==='failed'&&!failedState.quote,'Failure status must not authorize retry');
   check((await page.innerText('#aiStatus')).includes(failedState.message),'Failure hint not visible');
   const after=await page.request.get(new URL(`/artifact/${failure.scan_id}/result.json`,base).href);
   check(sha(await after.body())===digest,'Failed AI damaged deterministic result');
   check((await page.innerText('#evidenceTable')).length>0,'Evidence hidden on AI failure');
   fs.writeFileSync(path.join(out,'mock-failure-record.json'),JSON.stringify({at:new Date().toISOString(),passed:true,scope:'MOCK FAILURE ONLY',failed_state:failedState,...failure},null,2));await page.close();
  }
 }finally{await browser.close()}
 process.exitCode=result.every(r=>r.passed)?0:1;
})().catch(e=>{console.error(e);process.exitCode=1});
