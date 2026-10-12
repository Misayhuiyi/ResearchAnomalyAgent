/* Synthetic reference + explicitly mocked AI + real four-format report exports.
   Never run against a provider-backed or everyday workbench. */
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),base=process.env.DEMO_URL;
const out=path.resolve(process.env.PAPER_AUDIT_VERIFICATION_DIR||'');
if(base!=='http://127.0.0.1:8881/'||process.env.PAPER_AUDIT_AI_MOCK!=='EXPLICIT_TEST_ONLY'
 ||!out.startsWith(path.join(root,'docs','verification')+path.sep))throw Error('Explicit isolated mock and evidence directory required');
const check=(v,m)=>{if(!v)throw Error(m)},hash=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{const browser=await chromium.launch({headless:true});let passed=0;
 try{const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base,{waitUntil:'networkidle'});await page.click('#sampleBtn');
  await page.waitForFunction(()=>!document.getElementById('scanBtn').disabled);await page.click('#scanBtn');
  await page.waitForSelector('#resultView:not(.hidden)',{timeout:190000});
  const scan=await page.evaluate(()=>currentResult.scan_id);
  const resultURL=new URL(`/artifact/${scan}/result.json`,base).href;
  const original=await (await page.request.get(resultURL)).body();
  await page.locator('[data-finding]').first().click();
  await page.waitForFunction(()=>!document.getElementById('aiStatus').textContent.includes('正在读取'));
  await page.click('#aiQuoteBtn');await page.waitForSelector('#aiConfirmBtn:not(.hidden)');
  await page.click('#aiConfirmBtn');await page.waitForSelector('#aiOutput:not(.hidden)',{timeout:30000});
  check((await page.innerText('#aiWhat')).includes('固定差值'),'Mock explanation missing');passed++;
  const source=fs.readFileSync(path.join(root,'mvp-demo','samples','fixed_shift_demo.csv'),'utf8');
  check(source.includes('0.15,0.45'),'Synthetic source changed');
  const reference=source.replace('0.15,0.45','0.15,0.46');
  await page.setInputFiles('#referenceFileInput',{name:'reference.csv',mimeType:'text/csv',buffer:Buffer.from(reference)});
  await page.click('#referenceUpload');await page.waitForSelector('#referenceMapping:not(.hidden)');
  await page.waitForFunction(()=>!document.getElementById('referenceCompare').disabled);
  await page.locator('[data-reference-source="0"] [data-reference-key]').check();
  await page.click('#referenceCompare');await page.waitForFunction(()=>document.getElementById('referenceMessage').textContent==='版本核对已保存。');
  const comparisons=(await (await page.request.get(new URL(`/api/reference/${scan}`,base).href)).json()).comparisons;
  const comparison=comparisons[0];
  check(comparison.differences_total===1,'Incorrect reference difference count');
  const difference=comparison.differences[0];
  check(difference.source.row===2&&difference.source.column_idx===3,'Wrong physical position');
  check(String(difference.source.value)==='0.45'&&String(difference.reference.value)==='0.46','Full original values changed');passed++;
  await page.click('#freezeReport');await page.waitForSelector('#reportDownloads a',{timeout:180000});
  const reportDir=path.join(out,'additions-reports');fs.mkdirSync(reportDir,{recursive:true});
  const exports=[];
  for(const url of await page.locator('#reportDownloads a').evaluateAll(a=>a.map(x=>x.getAttribute('href')))){
   const response=await page.request.get(new URL(url,base).href);check(response.ok(),'Report unavailable');
   const bytes=await response.body(),name=url.split('/').pop();fs.writeFileSync(path.join(reportDir,name),bytes);
   exports.push({name,sha256:hash(bytes)});
   if(name==='report.html')check(bytes.toString().includes('辅助解释')&&bytes.toString().includes('版本数值差异'),'Snapshot omitted added contexts');
  }
  check(exports.length===4,'Four formats missing');passed++;
  await page.reload({waitUntil:'networkidle'});await page.evaluate(id=>openJob(id),scan);
  await page.waitForSelector('#referenceEvidence');await page.locator('[data-finding]').first().click();
  await page.waitForSelector('#aiOutput:not(.hidden)');
  check(hash(await (await page.request.get(resultURL)).body())===hash(original),'Original scan mutated');
  check(!errors.length,'Browser errors');passed++;
  fs.writeFileSync(path.join(out,'additions-browser.json'),JSON.stringify({passed,failed:0,scan_id:scan,
   source:'synthetic only',model:'MOCK ONLY',paid_calls:0,exports},null,2));
  console.log(JSON.stringify({passed,failed:0,paid_calls:0}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
