/* Local synthetic materials, real computation, persistence and document exports. */
const {chromium}=require('playwright');
const base=process.env.DEMO_URL;
if(!base||!['127.0.0.1','localhost'].includes(new URL(base).hostname)||new URL(base).port==='8765')throw Error('Use an isolated test server.');
(async()=>{
  const browser=await chromium.launch({headless:true});
  let passed=0;
  const assert=(ok,msg)=>{if(!ok)throw Error(msg)};
  const check=async(name,fn)=>{await fn();passed++;console.log('PASS '+name)};
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base,{waitUntil:'networkidle'});
    await check('更多核对项目默认不选，能提交新增方法',async()=>{
      await page.waitForSelector('[data-check="group_total"]',{state:'attached'});
      assert(await page.locator('[data-check]:checked').count()===0,'Unexpected default assumptions');
      await page.setInputFiles('#fileInput',{name:'分组核对.csv',mimeType:'text/csv',buffer:Buffer.from('总人数,分组1人数,分组2人数\n40,13,20\n40,13,27\n')});
      await page.click('#statOptions summary'); await page.locator('#statOptions details summary').click();
      await page.check('[data-check="group_total"]');await page.click('#scanBtn');
      await page.waitForSelector('#resultView:not(.hidden)',{timeout:190000});
      await page.locator('.finding').filter({hasText:'分组合计不一致'}).first().click();
      assert((await page.innerText('#evidenceTable')).includes('13'),'Original evidence absent');
      await page.waitForFunction(()=>!document.getElementById('saveReview').disabled);
    });
    await check('合理解释必须填写依据，保存后刷新保留',async()=>{
      await page.selectOption('#reviewState','explained');await page.click('#saveReview');
      await page.waitForFunction(()=>document.getElementById('reviewMessage').textContent.includes('依据'));
      await page.fill('#reviewNote','已核对原表，第二组人数应为27，待作者确认。');await page.click('#saveReview');
      await page.waitForFunction(()=>document.getElementById('reviewMessage').textContent==='复核已保存。');
      await page.click('#refreshReview');await page.waitForFunction(()=>!document.getElementById('saveReview').disabled);
      assert(await page.inputValue('#reviewNote')==='已核对原表，第二组人数应为27，待作者确认。','Review lost');
    });
    await check('并发页面旧版本不能覆盖，未保存说明保留',async()=>{
      const scan=await page.evaluate(()=>currentResult.scan_id);
      const view=(await (await context.request.get(base+'/api/reviews/'+scan)).json()).review;
      const fid=await page.evaluate(()=>selectedFinding);
      const res=await context.request.post(base+'/api/reviews',{data:{scan_id:scan,finding_id:fid,state:'further_check',note:'另一页面补充核查。',revision:view.revision,request_key:'browser-concurrent-01'}});
      assert(res.ok(),'Second page update failed');
      await page.fill('#reviewNote','当前页未保存的说明。');await page.click('#saveReview');
      await page.waitForFunction(()=>document.getElementById('reviewMessage').textContent.includes('其他页面'));
      assert(await page.inputValue('#reviewNote')==='当前页未保存的说明。','Unsaved draft lost');
      await page.click('#refreshReview');await page.waitForFunction(()=>!document.getElementById('saveReview').disabled);
      await page.click('#saveReview');await page.waitForFunction(()=>document.getElementById('reviewMessage').textContent==='复核已保存。');
    });
    await check('一次生成四种格式，内容来自同一冻结版本',async()=>{
      await page.click('#freezeReport');
      await page.waitForSelector('#reportDownloads a',{timeout:60000});
      assert(await page.locator('#reportDownloads a').count()===4,'Incomplete output');
      const urls=await page.locator('#reportDownloads a').evaluateAll(nodes=>nodes.map(n=>n.href));
      assert(new Set(urls.map(url=>url.split('/').slice(-2,-1)[0])).size===1,'Mixed report versions');
      for(const url of urls){const r=await context.request.get(url);assert(r.ok()&&(await r.body()).length>200,'Broken download '+url)}
      const report=await context.request.get(urls.find(url=>url.endsWith('.html')));
      assert((await report.text()).includes('当前页未保存的说明。'),'Report missing review');
      await page.screenshot({path:require('path').join(process.env.PAPER_AUDIT_SCREENSHOT_DIR||'docs/product','10_复核与冻结报告验证截图.png'),fullPage:true});
    });
    await check('历史结果重新打开后保留复核与已生成报告',async()=>{
      await page.reload({waitUntil:'networkidle'});await page.click('[data-view="jobs"]');
      await page.locator('[data-open-job]').first().click();
      await page.waitForSelector('#reportHistory a',{state:'attached'});
      await page.locator('#reportHistory').evaluate(node=>node.parentElement.open=true);
      await page.locator('.finding').filter({hasText:'分组合计不一致'}).first().click();
      assert(await page.inputValue('#reviewNote')==='当前页未保存的说明。','History missing review');
      assert(await page.locator('#reportHistory a').count()===3,'History missing exports');
    });
    await check('取消按钮停止真实检查并显示已停止',async()=>{
      await page.click('#sampleBtn');
      await page.waitForFunction(()=>!document.getElementById('scanBtn').disabled);
      await page.click('#scanBtn');await page.waitForFunction(()=>currentJobId&&busy);
      await page.click('#cancelScan');
      await page.waitForFunction(()=>!busy,{timeout:30000});
      assert((await page.innerText('#scanError')).includes('已停止'),'Cancellation did not stop task');
      const id=await page.evaluate(()=>currentJobId);
      const data=await (await context.request.get(base+'/api/jobs/'+id)).json();
      assert(data.job.status==='cancelled'&&!data.job.result,'Cancelled task exposed successful result');
    });
    await check('无页面脚本错误',async()=>assert(!errors.length,errors.join('\n')));
    console.log(`${passed}/${passed} PASS`);
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
