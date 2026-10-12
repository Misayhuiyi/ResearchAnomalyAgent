/* Real upload and PaperConan scan; model transport is replaced by a local mock. */
const {chromium}=require('playwright');
const base=process.env.DEMO_URL;
if(base!=='http://127.0.0.1:8881/')throw Error('Use the isolated AI mock server.');
(async()=>{
  const browser=await chromium.launch({headless:true});
  let passed=0;
  const check=async(name,fn)=>{await fn();passed++;console.log('PASS '+name)};
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base,{waitUntil:'networkidle'});
    await check('upload sample and scan with PaperConan',async()=>{
      await page.click('#sampleBtn');
      await page.waitForFunction(()=>!document.getElementById('scanBtn').disabled);
      await page.click('#scanBtn');
      await page.waitForSelector('#resultView:not(.hidden)',{timeout:190000});
      if(Number(await page.innerText('#statFindings'))<1)throw Error('No deterministic finding');
    });
    await check('search, filter, evidence and both JSON exports work',async()=>{
      await page.fill('#search','control');
      if(!await page.locator('[data-finding]').count())throw Error('Search failed');
      await page.fill('#search','');
      await page.locator('[data-finding]').first().click();
      if(!await page.locator('#evidenceTable tr').count())throw Error('Evidence missing');
      for(const id of ['jsonExportBtn','engineReportBtn']){
        const url=await page.locator('#'+id).getAttribute('href');
        const response=await page.request.get(new URL(url,base).href);
        if(!response.ok()||!(await response.text()).trim().startsWith('{'))throw Error('Export failed: '+id);
      }
    });
    await check('AI quote and explicit approval lead to bound explanation',async()=>{
      await page.click('#aiQuoteBtn');
      await page.waitForSelector('#aiConfirmBtn:not(.hidden)');
      if(!await page.innerText('#aiStatus').then(x=>x.includes('费用上限')))throw Error('No fee quote');
      await page.click('#aiConfirmBtn');
      await page.waitForSelector('#aiOutput:not(.hidden)',{timeout:30000});
      if(!await page.innerText('#aiBoundary').then(x=>x.includes('不代表科研不端结论')))throw Error('Boundary absent');
      if(!await page.innerText('#aiWhat').then(x=>x.includes('固定差值')))throw Error('Explanation absent');
    });
    await check('reload retains explanation and original deterministic result',async()=>{
      await page.reload({waitUntil:'networkidle'});
      await page.click('[data-view="jobs"]');
      await page.locator('[data-open-job]').first().click();
      await page.locator('[data-finding]').first().click();
      await page.waitForSelector('#aiOutput:not(.hidden)');
      if(Number(await page.innerText('#statFindings'))<1)throw Error('Scan lost');
      if(errors.length)throw Error(errors.join('; '));
    });
    console.log(JSON.stringify({passed,failed:0,model:'MOCK ONLY'}));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
