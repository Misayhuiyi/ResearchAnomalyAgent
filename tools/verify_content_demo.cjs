/* Explicit model substitute; real scope, consent, accounting, source reading and reports. */
const {chromium}=require('playwright');
const base=process.env.DEMO_URL;
if(!base||new URL(base).port!=='8877')throw Error('Independent synthetic fixture required');
(async()=>{const browser=await chromium.launch({headless:true});let passed=0;
const assert=(value,message)=>{if(!value)throw Error(message)};
const check=async(name,fn)=>{await fn();passed++;console.log('PASS '+name)};
try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base,{waitUntil:'networkidle'});let original;
 await check('未确认用途不能发起内容核对',async()=>{
  await page.click('#sampleBtn');await page.waitForFunction(()=>!document.getElementById('scanBtn').disabled);await page.click('#scanBtn');
  await page.waitForSelector('#resultView:not(.hidden)',{timeout:190000});await page.waitForFunction(()=>!document.getElementById('prepareContent').disabled);
  original=await page.evaluate(()=>currentResult.scan_id);await page.click('#prepareContent');
  assert((await page.innerText('#contentMessage')).includes('确认每份材料'),'Missing role confirmation');
 });
 await check('预估不执行，明确确认后才产生核对结果',async()=>{
  await page.locator('#contentRoles select').selectOption('table');await page.click('#prepareContent');await page.waitForSelector('#startContent:not(.hidden)');
  let state=(await (await page.request.get(base+'/api/content/'+original)).json()).content;
  assert(state.spent_micros===0&&state.next_step===0,'Charged before consent');
  assert((await page.innerText('#contentScope')).includes('DeepSeek V4.1 Flash'),'Model not disclosed');
  await page.click('#startContent');await page.waitForFunction(()=>document.getElementById('contentMessage').textContent.includes('核对结束'),{timeout:30000});
  assert((await page.innerText('#contentEvidence')).includes('fixed_shift_demo.csv'),'No original citation');
  const review=(await (await page.request.get(base+'/api/reviews/'+original)).json()).review;
  assert(review.revision===0&&Object.keys(review.reviews).length===0,'Model modified user review');
 });
 await check('冻结报告包含同一版原文依据与费用',async()=>{
  await page.click('#freezeReport');await page.waitForSelector('#reportDownloads a',{timeout:60000});
  const url=await page.locator('#reportDownloads a').filter({hasText:'HTML'}).getAttribute('href');
  const report=await (await page.request.get(base+url)).text();assert(report.includes('原文核对建议')&&report.includes('累计授权上限'),'Content report incomplete');
 });
 await check('刷新与重复打开不重置费用',async()=>{
  const before=(await (await page.request.get(base+'/api/content/'+original)).json()).content;
  await page.reload({waitUntil:'networkidle'});await page.evaluate(id=>openJob(id),original);
  await page.waitForFunction(()=>document.getElementById('contentMessage').textContent.includes('核对结束'));
  const after=(await (await page.request.get(base+'/api/content/'+original)).json()).content;
  assert(before.budget_id===after.budget_id&&before.spent_micros===after.spent_micros,'Budget reset');
 });
 await check('补充材料创建新版本，旧报告与费用不变',async()=>{
  await page.click('#newMaterialVersion');assert((await page.innerText('#versionNotice')).includes('旧版本不变'),'Version notice absent');
  await page.setInputFiles('#fileInput',{name:'supplement.csv',mimeType:'text/csv',buffer:Buffer.from('a,b\n1,2\n2,3\n3,4\n4,5\n5,6\n')});
  await page.waitForFunction(()=>!document.getElementById('scanBtn').disabled);await page.click('#scanBtn');await page.waitForFunction(id=>currentResult&&currentResult.scan_id!==id,original,{timeout:190000});
  const next=await page.evaluate(()=>currentResult.scan_id);const data=await (await page.request.get(base+'/api/versions/'+next)).json();
  assert(data.versions.length===2&&data.versions.some(v=>v.parent_scan===original),'No lineage');
  const state=(await (await page.request.get(base+'/api/content/'+next)).json()).content;assert(state.status==='not_started','Old content approval migrated');
  assert((await (await page.request.get(base+'/api/reviews/'+next)).json()).review.revision===0,'Old review migrated');
 });
 await check('页面无脚本错误',async()=>assert(!errors.length,errors.join('\n')));
 await page.screenshot({path:require('path').join(process.env.PAPER_AUDIT_SCREENSHOT_DIR||'docs/product','11_内容核对与材料版本验证截图.png'),fullPage:true});
 console.log(`${passed}/${passed} PASS`);
}finally{await browser.close()}})().catch(error=>{console.error(error);process.exitCode=1});
