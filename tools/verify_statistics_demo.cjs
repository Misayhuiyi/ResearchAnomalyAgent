/* Synthetic inputs, real local engine and arithmetic; never writes daily history. */
const {chromium} = require('playwright');
const base = process.env.DEMO_URL;
if (!base || !['127.0.0.1','localhost'].includes(new URL(base).hostname) || new URL(base).port === '8765')
  throw Error('Use an isolated local test server, not the daily 8765 service.');
const sample = '分组,人数,总人数,百分比,样本量,标准差,标准误\nA,13,40,32.5%,25,10.00,2.00\nB,13,40,25.0%,25,10.00,3.00\nC,1,3,33.3%,10,1.20,0.38\nD,4,0,10.0%,1,1.00,1.00\n';
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const assert = (ok, message) => {if (!ok) throw Error(message);};
    let passed=0;
    async function check(name, run) {await run(); passed++; console.log('PASS  '+name);}
    async function upload(name, value) {await page.setInputFiles('#fileInput',{name,mimeType:'text/csv',buffer:Buffer.from(value,'utf8')});}
    async function scan() {
      await page.waitForFunction(()=>!document.getElementById('scanBtn').disabled);
      await page.click('#scanBtn');
      await page.waitForSelector('#resultView:not(.hidden)', {timeout:190000});
    }
    await page.goto(base,{waitUntil:'networkidle'});
    await page.click('#statOptions summary');
    await check('统计核对默认关闭，材料变更撤回旧口径确认',async()=>{
      assert(!await page.isChecked('#checkPercent') && !await page.isChecked('#checkSE'),'Selected by default');
      await page.check('#checkPercent');
      await upload('statistics.csv',sample);
      assert(!await page.isChecked('#checkPercent'),'Consent carried over to new materials');
    });
    await check('提交真实计算并锁定处理中选项',async()=>{
      await page.check('#checkPercent'); await page.check('#checkSE');
      await page.waitForFunction(()=>!document.getElementById('scanBtn').disabled);
      const submitted=page.waitForRequest(r=>r.url().endsWith('/api/jobs') && r.method()==='POST');
      await page.click('#scanBtn');
      assert(await page.isDisabled('#checkPercent'),'Options editable while running');
      const request=await submitted;
      assert(JSON.stringify(request.postDataJSON().extra_checks)==='["count_percent","sd_se"]','Wrong API options');
      await page.waitForSelector('#resultView:not(.hidden)',{timeout:190000});
      assert((await page.innerText('#scanStatus')).includes('部分'),'Skipped rows reported as complete');
      assert((await page.innerText('#statisticsList')).includes('已核对 3 行 · 跳过 1 行'),'Coverage missing');
    });
    await check('人数结果定位第3行，显示13、40、25.0%与计算值',async()=>{
      await page.locator('.finding').filter({hasText:'人数与百分比不一致'}).click();
      assert((await page.innerText('#detailLocation')).includes('第 3 行'),'Wrong source row');
      const evidence=await page.innerText('#evidenceTable');
      assert(evidence.includes('13')&&evidence.includes('40')&&evidence.includes('25.0%'),'Missing original values');
      assert((await page.innerText('#detailKv')).includes('32.5'),'Calculated value missing');
      await page.screenshot({path:require('path').join(process.env.PAPER_AUDIT_SCREENSHOT_DIR||'docs/product','09_统计核对原始数值验证截图.png'),fullPage:true});
    });
    await check('标准差结果保留10.00、3.00，未把舍入相符行误报',async()=>{
      assert(await page.locator('.finding').filter({hasText:'标准差与标准误不一致'}).count()===1,'False positive');
      await page.locator('.finding').filter({hasText:'标准差与标准误不一致'}).click();
      const evidence=await page.innerText('#evidenceTable');
      assert(evidence.includes('10.00')&&evidence.includes('3.00'),'Lost original precision');
      assert((await page.innerText('#detailLocation')).includes('第 3 行'),'Wrong SE row');
    });
    await check('报告与历史保留原值、确认口径和跳过原因',async()=>{
      const response=await context.request.get(new URL(await page.getAttribute('#rawReport','href'),base).href);
      const report=await response.text();
      assert(response.ok()&&report.includes('25.0%')&&report.includes('用户确认的口径')&&report.includes('统计核对范围'),'Incomplete report');
      await page.reload({waitUntil:'networkidle'});
      await page.click('[data-view="jobs"]');
      assert((await page.locator('.job').first().innerText()).includes('部分完成'),'History lost partial status');
      await page.locator('[data-open-job]').first().click();
      await page.waitForSelector('#scanView:not(.hidden) #resultView:not(.hidden)');
      assert((await page.innerText('#statisticsList')).includes('跳过 1 行'),'History lost coverage');
    });
    await check('缺列明确标记未能核对，不能显示全部完成',async()=>{
      await upload('missing.csv','group,value\nA,1\nB,2\nC,3\n');
      await page.click('#statOptions summary'); await page.check('#checkSE');
      await scan();
      const coverage=await page.innerText('#statisticsList');
      assert(coverage.includes('未能核对')&&coverage.includes('缺少明确的列名'),'Missing column explanation absent');
      assert((await page.innerText('#scanStatus')).includes('部分'),'Missing columns reported complete');
      await page.click('[data-remove-file]');
      assert(!await page.isChecked('#checkSE'),'Removed material kept consent');
    });
    await check('移动宽度可操作且无未处理脚本错误',async()=>{
      await page.setViewportSize({width:390,height:844});
      assert(await page.locator('#scanBtn').isVisible(),'Mobile action missing');
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Page overflow');
      assert(!errors.length, errors.join('\n'));
    });
    console.log(`SUMMARY ${passed}/${passed} passed; synthetic CSV, real engine and arithmetic`);
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
