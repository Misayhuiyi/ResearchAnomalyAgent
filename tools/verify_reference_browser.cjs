/* Real original/corrected materials, no model or response interception. */
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.env.PAPER_CORPUS_RESULTS||''),base=process.env.DEMO_URL;
if(!out.startsWith(path.join(root,'test-results')+path.sep)||new URL(base).hostname!=='127.0.0.1')throw Error('Isolated local test required');
const scans=JSON.parse(fs.readFileSync(path.join(out,'browser-summary.json'))).cases;
const check=(v,m)=>{if(!v)throw Error(m)},sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const cases=[{id:'E01_Iris已知录入差异',source:'iris_uci.csv',reference:'test-corpus/cases/B03_Iris按来源修正/iris_corrected.csv',
  sourceSheet:'iris_uci',referenceSheet:'iris_corrected',keys:[],expected:3,coordinates:[[36,4],[39,2],[39,3]]},
 {id:'E02_运动实验录入错误',source:'original.xlsx',reference:'test-corpus/cases/B04_运动实验修正版/corrected.xlsx',
  sourceSheet:'Experiment 2',referenceSheet:'Experiment 2',keys:[1],expected:1,coordinates:[[6,11]]}];
(async()=>{const browser=await chromium.launch({headless:true}),records=[];
 try{for(const c of cases){const record={case_id:c.id,at:new Date().toISOString(),passed:false,model_calls:0},page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  try{
   const scan=scans.find(r=>r.case_id===c.id).scan_id;record.scan_id=scan;
   await page.goto(base,{waitUntil:'networkidle'});await page.evaluate(id=>openJob(id),scan);await page.waitForSelector('#resultView:not(.hidden)');
   const before=await page.request.get(new URL(`/artifact/${scan}/result.json`,base).href),hash=sha(await before.body());
   await page.selectOption('#referenceSourceFile',c.source);await page.setInputFiles('#referenceFileInput',path.join(root,c.reference));
   await page.click('#referenceUpload');await page.waitForSelector('#referenceMapping:not(.hidden)');
   await page.waitForFunction(()=>!document.getElementById('referenceCompare').disabled);
   await page.selectOption('#referenceSourceSheet',c.sourceSheet);await page.selectOption('#referenceSheet',c.referenceSheet);
   if(c.keys.length){for(const index of c.keys)await page.locator(`[data-reference-source="${index}"] [data-reference-key]`).check();}
   else{
    await page.click('#referenceCompare');await page.waitForFunction(()=>document.getElementById('referenceMessage').textContent.includes('确认'));
    check(!await page.locator('#referenceEvidence').count(),'Unconfirmed order produced differences');
    await page.check('#referenceOrderConfirm');
   }
   await page.click('#referenceCompare');await page.waitForFunction(()=>document.getElementById('referenceMessage').textContent==='版本核对已保存。');
   const response=await page.request.get(new URL('/api/reference/'+scan,base).href),r=(await response.json()).comparisons[0];
   check(r.differences_total===c.expected,'Real correction differences wrong');check(r.unmatched_rows.length===0,'Unexpected unmatched rows');
   for(const [row,col] of c.coordinates)check(r.differences.some(d=>d.source.row===row&&d.source.column_idx===col),'Corrected source position absent');
   check((await page.innerText('#referenceResults')).includes('不能据此判断哪一版正确'),'Boundary not visible');
   if(c.expected===1){const text=await page.innerText('#referenceEvidence');check(text.includes('65.95549826312603')&&text.includes('68.88')&&text.includes('VO2maxVB'),'Original/full corrected value missing');}
   await page.click('#freezeReport');await page.waitForSelector('#reportDownloads a',{timeout:180000});
   const folder=path.join(out,c.id,'reference-verified');fs.mkdirSync(folder,{recursive:true});
   fs.writeFileSync(path.join(folder,'comparison.json'),JSON.stringify(r,null,2));
   for(const link of await page.locator('#reportDownloads a').evaluateAll(a=>a.map(x=>x.getAttribute('href')))){
    const name=link.split('/').pop(),download=await page.request.get(new URL(link,base).href);check(download.ok(),'Export after reference failed');
    const buffer=await download.body();fs.writeFileSync(path.join(folder,name),buffer);
    if(name==='report.html')check(buffer.toString().includes('版本数值差异'),'Reference not in report');
   }
   await page.locator('#referenceResults').scrollIntoViewIfNeeded();
   await page.screenshot({path:path.join(folder,'reference-evidence.png'),fullPage:false});
   await page.reload({waitUntil:'networkidle'});await page.evaluate(id=>openJob(id),scan);await page.waitForSelector('#referenceEvidence');
   check((await page.innerText('#referenceResults')).includes(`${c.expected} 处差异`),'Comparison not retained');
   const after=await page.request.get(new URL(`/artifact/${scan}/result.json`,base).href);check(sha(await after.body())===hash,'Reference edited deterministic source');
   check(!errors.length,errors.join('; '));record.passed=true;record.differences=c.expected;record.comparison=r;
  }catch(e){record.error=e.message;}
  finally{records.push(record);await page.close();fs.writeFileSync(path.join(out,'reference-browser.json'),JSON.stringify({at:new Date().toISOString(),records,passed:records.filter(r=>r.passed).length,failed:records.filter(r=>!r.passed).length,model_calls:0},null,2));console.log(JSON.stringify({case:c.id,passed:record.passed,error:record.error||null}));}
 }}finally{await browser.close()}
 process.exitCode=records.every(r=>r.passed)?0:1;
})().catch(e=>{console.error(e);process.exitCode=1});
