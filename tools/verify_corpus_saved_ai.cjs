/* Inspect already paid/persisted replies. Does not quote or invoke the provider. */
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.env.PAPER_CORPUS_RESULTS||''),base=process.env.DEMO_URL;
if(!out.startsWith(path.join(root,'test-results')+path.sep)||new URL(base).hostname!=='127.0.0.1')throw Error('Isolated local verification required');
const records=JSON.parse(fs.readFileSync(path.join(out,'live-ai-summary.json'))).records;
const check=(v,m)=>{if(!v)throw Error(m)},sha=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{const browser=await chromium.launch({headless:true}),results=[];
 try{
  for(const record of records){const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
   const result={case_id:record.case_id,scan_id:record.scan_id,finding_id:record.finding_id,at:new Date().toISOString(),passed:false,paid_calls_added:0};
   const blockPaid=async route=>{throw Error('This verifier must not call any paid endpoint')};
   await page.route('**/api/explanations/run',blockPaid);
   try{
    const source=await page.request.get(new URL(`/artifact/${record.scan_id}/result.json`,base).href),sourceHash=sha(await source.body());
    await page.goto(base,{waitUntil:'networkidle'});await page.evaluate(id=>openJob(id),record.scan_id);
    await page.waitForSelector('#resultView:not(.hidden)');await page.locator(`[data-finding="${record.finding_id}"]`).click();
    await page.waitForSelector('#aiOutput:not(.hidden)');
    check(await page.innerText('#aiWhat')===record.state.explanation.what,'Persisted explanation differs');
    check((await page.innerText('#aiBoundary')).includes('不能判断作者意图'),'Boundary missing');
    check(await page.locator('#aiConfirmBtn:not(.hidden)').count()===0,'Completed finding unexpectedly requests payment');
    await page.waitForFunction(()=>!document.getElementById('freezeReport').disabled);
    await page.click('#freezeReport');await page.waitForSelector('#reportDownloads a',{timeout:180000});
    const links=await page.locator('#reportDownloads a').evaluateAll(a=>a.map(x=>x.getAttribute('href')));
    check(links.length===4,'Report formats missing after AI');
    const folder=path.join(out,record.case_id,'after-ai');fs.mkdirSync(folder,{recursive:true});result.exports={};
    for(const link of links){const response=await page.request.get(new URL(link,base).href),name=link.split('/').pop();
     check(response.ok(),'Report after AI failed');const bytes=await response.body();fs.writeFileSync(path.join(folder,name),bytes);
     result.exports[name]={sha256:sha(bytes),size:bytes.length};
     if(name==='report.html'){
      const expected=record.state.explanation.what.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
      result.frozen_report_contains_finding_ai=bytes.toString('utf8').includes(expected);
      check(result.frozen_report_contains_finding_ai,'Saved AI explanation is missing from frozen report');
     }
    }
    fs.copyFileSync(path.join(out,record.case_id,'智能解释.json'),path.join(folder,'智能解释.json'));
    const after=await page.request.get(new URL(`/artifact/${record.scan_id}/result.json`,base).href);
    check(sha(await after.body())===sourceHash,'AI/report changed deterministic result');check(!errors.length,errors.join('; '));
    await page.screenshot({path:path.join(out,record.case_id,'live-ai-verified.png'),fullPage:false});result.passed=true;
   }catch(e){result.error=e.message;}
   finally{await page.close();results.push(result);fs.writeFileSync(path.join(out,'saved-ai-browser.json'),JSON.stringify({at:new Date().toISOString(),
    paid_calls_added:0,records:results,passed:results.filter(x=>x.passed).length,failed:results.filter(x=>!x.passed).length,
    export_boundary:'All four new frozen reports include the source-bound saved finding AI explanation; older frozen reports stay immutable.'},null,2));
    console.log(JSON.stringify({case:result.case_id,passed:result.passed,error:result.error||null}));}
  }
 }finally{await browser.close()}
 process.exitCode=results.every(x=>x.passed)?0:1;
})().catch(e=>{console.error(e);process.exitCode=1});
