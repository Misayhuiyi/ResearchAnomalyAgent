const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const base = process.env.DEMO_URL;
if (!base || new URL(base).port !== '8877') throw Error('Use the explicit 8877 material fixture.');

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    const checkFixture = await (await context.request.get(new URL('/__fixture__', base).href)).json();
    if (!checkFixture.fixture) throw Error('Not a fixture server');
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const assert = (truth, message) => { if (!truth) throw Error(message); };
    const rows = [];
    async function check(name, run) { await run(); rows.push(name); console.log('PASS  ' + name); }
    await page.goto(base, {waitUntil:'networkidle'});
    await check('空输入有明确提示', async () => {
      await page.click('#discoverBtn');
      assert((await page.innerText('#sourceMessage')).includes('请输入'), 'Missing empty-input prompt');
    });
    await check('查找候选、标题安全显示、确认前不能加入', async () => {
      await page.fill('#paperReference', 'https://fixtures.example/paper');
      await page.click('#discoverBtn');
      await page.waitForSelector('#sourceResults:not(.hidden)');
      assert((await page.innerText('#paperTitle')).includes('<script>'), 'Title not treated as text');
      assert(await page.locator('#sourceCandidates button').count() === 2, 'Candidate count');
      assert(await page.locator('#sourceCandidates button').first().isDisabled(), 'Import did not require confirmation');
    });
    await check('获取材料后可移除并重新加入', async () => {
      await page.check('#sourceConfirm');
      await page.locator('#sourceCandidates button').first().click();
      await page.waitForSelector('[data-remove-file]');
      assert((await page.innerText('#fileList')).includes('public-data.csv'), 'Downloaded file not selected');
      await page.click('[data-remove-file]');
      assert(await page.locator('#sourceCandidates button').first().isEnabled(), 'Removed material cannot be re-added');
      await page.locator('#sourceCandidates button').first().click();
      await page.waitForSelector('[data-remove-file]');
    });
    await check('登录网页不冒充文件、不清空已有材料', async () => {
      await page.locator('#sourceCandidates button').nth(1).click();
      await page.waitForFunction(() => document.getElementById('sourceMessage').textContent.includes('网页'));
      assert(await page.locator('[data-remove-file]').count() === 1, 'Existing selection lost');
    });
    await check('公开材料与本地上传一起执行真实筛查', async () => {
      await page.setInputFiles('#fileInput', {name:'local-data.csv',mimeType:'text/csv',buffer:fs.readFileSync(path.resolve('mvp-demo/samples/fixed_shift_demo.csv'))});
      await page.waitForFunction(() => !document.getElementById('scanBtn').disabled);
      await page.click('#scanBtn');
      await page.waitForSelector('#resultView:not(.hidden)', {timeout:190000});
      assert((await page.innerText('#statFiles')) === '2', 'Wrong material count');
      assert(Number(await page.innerText('#statFindings')) > 0, 'No real engine results');
      await page.locator('#materialsDetails summary').click();
      assert((await page.innerText('#materialsList')).includes('https://fixtures.example/public-data.csv'), 'Missing source URL');
      const report = await (await context.request.get(new URL(await page.getAttribute('#rawReport','href'), base).href)).text();
      assert(report.includes('https://fixtures.example/public-data.csv'), 'Report lost original source');
      assert(report.includes('用户上传'), 'Local file provenance missing');
    });
    await check('历史重开保留材料来源', async () => {
      await page.reload({waitUntil:'networkidle'});
      await page.click('[data-view="jobs"]');
      await page.locator('[data-open-job]').first().click();
      await page.waitForSelector('#resultView:not(.hidden)');
      assert((await page.locator('#materialsList').textContent()).includes('https://fixtures.example/public-data.csv'), 'History lost source');
    });
    await check('页面无未处理脚本错误', async () => assert(!errors.length, errors.join('\n')));
    await page.screenshot({path:require('path').join(process.env.PAPER_AUDIT_SCREENSHOT_DIR||'docs/product','08_公开材料入口验证截图.png'),fullPage:true});
    console.log(`SUMMARY ${rows.length}/${rows.length} passed; public website substituted, engine real`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
