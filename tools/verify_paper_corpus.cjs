/* REAL browser uploads/scans/reviews/exports. Never clicks a paid confirmation. */
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),corpus=path.join(root,'test-corpus');
const out=path.resolve(process.env.PAPER_CORPUS_RESULTS||'');
const base=process.env.DEMO_URL;
if(!out.startsWith(path.join(root,'test-results')+path.sep))throw Error('Use isolated test-results directory.');
if(!base||new URL(base).hostname!=='127.0.0.1'||['8765','8878'].includes(new URL(base).port))throw Error('Use an isolated loopback server.');
const manifest=JSON.parse(fs.readFileSync(path.join(corpus,'manifest.json')));
const selected=process.env.PAPER_CORPUS_CASES?.split(',');
const cases=manifest.cases.filter(c=>!selected||selected.includes(c.id));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const check=(v,m)=>{if(!v)throw Error(m)};
fs.mkdirSync(out,{recursive:true});
const records=[];
async function storeResponse(page,url,target){
 const response=await page.request.get(new URL(url,base).href,{timeout:180000});
 check(response.ok(),`Download failed ${target}`);const bytes=await response.body();check(bytes.length>20,'Empty artifact');
 fs.writeFileSync(target,bytes);return {size:bytes.length,sha256:sha(bytes)};
}
function expectations(c,r){
 const findings=r.findings, checks=[];
 for(const e of c.expected.relations||[]){
  const match=findings.find(f=>f.kind===e.kind&&f.n===e.n&&(!e.parameter||Math.abs(f.raw[e.parameter]-e.value)<1e-8));
  checks.push({expected:e,matched:match?.id||null,passed:!!match});
 }
 if(c.expected.rounding){const e=c.expected.rounding;
  const match=findings.find(f=>f.kind==='identical_after_rounding'&&f.n===e.n&&f.raw.rounded_to===e.rounded_to&&
    e.originals.every(x=>f.evidence.focus_cells.some(cell=>cell.original===x)));
  checks.push({expected:e,matched:match?.id||null,passed:!!match});
 }
 return checks;
}
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const c of cases){
   const dir=path.join(out,c.id);fs.mkdirSync(dir,{recursive:true});
   const record={case_id:c.id,title:c.title,group:c.group,profile:c.profile,at:new Date().toISOString(),
      steps:[],passed:false,model_calls:0,human_acceptance:'pending'};
   const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));const started=Date.now();
   try{
    for(const file of c.uploads)check(sha(fs.readFileSync(path.join(corpus,file)))===manifest.hashes[file],`Source changed: ${file}`);
    record.steps.push('upload snapshot hashes verified');
    await page.goto(base,{waitUntil:'networkidle'});
    await page.setInputFiles('#fileInput',c.uploads.map(p=>path.join(corpus,p)));
    await page.selectOption('#profile',c.profile);
    await page.waitForFunction(()=>!document.getElementById('scanBtn').disabled);
    await page.click('#scanBtn');
    await page.waitForSelector('#resultView:not(.hidden)',{timeout:220000});
    const result=await page.evaluate(()=>currentResult);record.scan_id=result.scan_id;
    record.summary=result.summary;record.scan_status=result.scan_status;record.materials=result.materials;
    check(result.materials.length===c.uploads.length,'Material inventory mismatch');
    check(result.summary.numeric_cells>0,'No numeric data read');
    check(result.profile===c.profile,'Profile not applied');
    check(!result.evidence_limits?.length,'Source evidence capacity exceeded');
    record.steps.push('actual browser upload and PaperConan job completed; coverage retained');
    record.expected_checks=expectations(c,result);
    // Do not abort later cases or suppress exports when an expected positive is missed.
    record.expected_passed=record.expected_checks.every(x=>x.passed);
    const finding=result.findings.find(f=>record.expected_checks.some(x=>x.matched===f.id))||
                  result.findings.find(f=>c.uploads.some(u=>u.endsWith('/'+f.file)&&!u.endsWith('.pdf')))||result.findings[0];
    if(finding){
     record.selected_finding=finding.id;
     await page.locator(`[data-finding="${finding.id}"]`).click();
     check((await page.innerText('#detailKv')).trim().length>0,'Detail not shown');
     check((await page.innerText('#evidenceTable')).trim().length>0,'Evidence not shown');
     await page.fill('#search',finding.file);
     check(await page.locator(`[data-finding="${finding.id}"]`).count()===1,'Search hides matching source');
     await page.fill('#search','');await page.selectOption('#severity',finding.severity);
     check(await page.locator(`[data-finding="${finding.id}"]`).count()===1,'Risk filter inconsistent');
     await page.selectOption('#severity','all');record.steps.push('finding detail, evidence, source search, risk filter');
     await page.waitForFunction(()=>!document.getElementById('saveReview').disabled);
     await page.selectOption('#reviewState','further_check');
     await page.fill('#reviewNote','工具回归测试记录：需要人工核对；不是论文错误或不端结论。');
     await page.click('#saveReview');await page.waitForFunction(()=>document.getElementById('reviewMessage').textContent==='复核已保存。');
     record.steps.push('neutral test-only review saved separately from source');
     // A quote does not call the provider. Await user fee authorization outside this runner.
     await page.click('#aiQuoteBtn');
     await page.waitForFunction(()=>!document.getElementById('aiConfirmBtn').classList.contains('hidden')||
       (!document.getElementById('aiQuoteBtn').disabled&&!document.getElementById('aiStatus').textContent.includes('正在')));
     const resp=await page.request.get(new URL(`/api/explanations/${result.scan_id}/${finding.id}`,base).href);
     record.ai_quote=(await resp.json()).ai;record.steps.push('AI fee preview only; NO paid confirmation');
    }else{record.steps.push('no findings: review and AI are not applicable; no invented clue');}
    record.artifacts={};
    for(const [key,name] of [['result_json','result.json'],['raw_scan','paperconan-scan.json'],['user_report','scan-report.html']])
      record.artifacts[name]=await storeResponse(page,result.artifacts[key],path.join(dir,name));
    const sourceDigest=record.artifacts['result.json'].sha256;
    await page.waitForFunction(()=>!document.getElementById('freezeReport').disabled);
    await page.click('#freezeReport');await page.waitForSelector('#reportDownloads a',{timeout:180000});
    const links=await page.locator('#reportDownloads a').evaluateAll(a=>a.map(x=>({name:x.textContent,href:x.getAttribute('href')})));
    check(links.length===4,'Four report formats missing');
    for(const link of links){const name=decodeURIComponent(link.href.split('/').pop());record.artifacts[name]=await storeResponse(page,link.href,path.join(dir,name));}
    record.steps.push('JSON/raw engine/HTML plus frozen Word, PDF, Excel, HTML downloaded');
    await page.screenshot({path:path.join(dir,'evidence.png'),fullPage:false});
    await page.reload({waitUntil:'networkidle'});await page.evaluate(id=>openJob(id),result.scan_id);
    await page.waitForSelector('#resultView:not(.hidden)');
    const reread=await page.evaluate(()=>currentResult);
    check(reread.scan_id===result.scan_id,'History reopened another scan');
    const response=await page.request.get(new URL(result.artifacts.result_json,base).href);
    check(sha(await response.body())===sourceDigest,'Review or quote changed deterministic results');
    if(finding){
     await page.locator(`[data-finding="${finding.id}"]`).click();
     await page.waitForFunction(()=>!document.getElementById('saveReview').disabled);
     check(await page.inputValue('#reviewState')==='further_check','Review not retained');
    }
    check(!errors.length,errors.join('; '));record.steps.push('history and review persist; source unchanged; no page script errors');
    record.workflow_passed=true;record.passed=record.expected_passed;
   }catch(e){record.error=e.message;record.workflow_passed=false;record.page_errors=errors;
    await page.screenshot({path:path.join(dir,'failure.png'),fullPage:false}).catch(()=>{});
   }finally{
    record.duration_ms=Date.now()-started;records.push(record);
    fs.writeFileSync(path.join(dir,'browser-record.json'),JSON.stringify(record,null,2));
    fs.writeFileSync(path.join(out,'browser-summary.json'),JSON.stringify({at:new Date().toISOString(),manifest_sha256:sha(fs.readFileSync(path.join(corpus,'manifest.json'))),
      scope:'REAL UI and PaperConan; no model calls; known-error recall is separate',cases:records,passed:records.filter(x=>x.passed).length,failed:records.filter(x=>!x.passed).length},null,2));
    console.log(JSON.stringify({case:c.id,passed:record.passed,findings:record.summary?.findings,status:record.scan_status,error:record.error||null}));
    await page.close();
   }
  }
 }finally{await browser.close()}
 process.exitCode=records.every(x=>x.passed)?0:1;
})().catch(e=>{console.error(e);process.exitCode=1});
