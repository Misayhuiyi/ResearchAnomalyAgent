const path = require("path");
const { chromium } = require("playwright");

const baseUrl = process.env.DEMO_URL || "http://127.0.0.1:8765/";

async function expectText(page, selector, expected) {
  const value = await page.locator(selector).innerText();
  if (!value.includes(expected)) {
    throw new Error(`${selector} 应包含“${expected}”，实际为“${value}”`);
  }
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const failures = [];
  const results = [];

  async function check(name, task) {
    try {
      await task();
      results.push([name, "PASS"]);
    } catch (error) {
      results.push([name, `FAIL：${error.message}`]);
      failures.push(name);
    }
  }

  await page.goto(baseUrl, { waitUntil: "networkidle" });

  await check("首屏只保留三项真实功能入口", async () => {
    if (await page.locator("[data-view]").count() !== 3) throw new Error("主导航不是 3 项");
    await expectText(page, "body", "上传材料");
    await expectText(page, "body", "结果用于辅助核对");
    const visible = await page.locator("body").innerText();
    for (const jargon of ["PaperConan", "Agent", "JSON", "queued", "running", "确定性", "线索编号", "为什么需要查看", "常见正常原因"]) {
      if (visible.includes(jargon)) throw new Error(`首屏出现技术术语：${jargon}`);
    }
  });

  await check("使用说明页面", async () => {
    await page.click('[data-view="about"]');
    await expectText(page, "#aboutView", "回到原表核对");
    await expectText(page, "#aboutView", "不能单独认定科研不端");
  });

  await check("筛查记录读取真实数据", async () => {
    await page.click('[data-view="jobs"]');
    await page.waitForSelector("#jobList");
    await expectText(page, "#jobsView", "重新启动后仍可查看");
  });

  await check("载入样例并创建真实后台任务", async () => {
    await page.click('[data-view="scan"]');
    await page.click("#sampleBtn");
    await page.waitForFunction(() => document.getElementById("fileName").textContent.includes("fixed_shift_demo.csv"));
    await expectText(page, "#fileCard", "fixed_shift_demo.csv");
    await page.waitForFunction(() => !document.getElementById("scanBtn").disabled);
    await page.click("#scanBtn");
    await page.waitForSelector("#resultView:not(.hidden)", { timeout: 190000 });
    await expectText(page, "#scanStatus", "检查完成");
    const count = Number(await page.locator("#statFindings").innerText());
    if (!Number.isFinite(count) || count < 1) throw new Error(`线索数异常：${count}`);
  });

  await check("问题筛选与数据详情", async () => {
    await page.locator("[data-finding]").first().click();
    await page.waitForSelector("#detail:not(.hidden)");
    await expectText(page, "#detail", "数据关系");
    await expectText(page, "#detail", "命中的原始数值");
    const roundingFinding = page.locator("[data-finding]").filter({ hasText: "4 个数值若保留 1 位小数均为 0.5" }).first();
    await roundingFinding.click();
    await expectText(page, "#detailTitle", "小数显示重复");
    await expectText(page, "#detailKv", "treated、control、scaled");
    const evidenceText = await page.locator("#evidenceTable").innerText();
    for (const expected of ["完整原始数值", "0.45", "0.47", "0.53", "0.46", "27"]) {
      if (!evidenceText.includes(expected)) throw new Error(`未显示命中位置或原始数值：${expected}`);
    }
    if (evidenceText.includes("见原始数据")) throw new Error("仍然使用模糊的原始数据提示");
    const visible = await page.locator("#resultView").innerText();
    if (/FD-\d+/.test(visible)) throw new Error("页面展示了内部线索编号");
    for (const phrase of ["为什么需要查看", "常见正常原因", "该模式需要结合", "系统在"]) {
      if (visible.includes(phrase)) throw new Error(`结果页出现多余解释：${phrase}`);
    }
    await page.screenshot({
      path: path.resolve(process.env.PAPER_AUDIT_SCREENSHOT_DIR || path.join(process.cwd(), "docs", "product"), "06_精简版HTML验证截图.png"),
      fullPage: true,
    });
  });

  await check("用户报告可直接阅读", async () => {
    const [reportPage] = await Promise.all([
      context.waitForEvent("page"),
      page.click("#rawReport"),
    ]);
    await reportPage.waitForLoadState("domcontentloaded");
    await expectText(reportPage, "body", "科研数据筛查报告");
    await expectText(reportPage, "body", "均高 0.3");
    const reportText = await reportPage.locator("body").innerText();
    if (reportText.includes("PaperConan") || /FD-\d+/.test(reportText)) throw new Error("报告包含内部术语或编号");
    await reportPage.close();
  });

  await check("筛查报告可真实下载", async () => {
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 10000 }),
      page.click("#exportBtn"),
    ]);
    if (!download.suggestedFilename().endsWith("-筛查报告.html")) throw new Error("下载文件名不正确");
  });

  await check("成功结果可从筛查记录重新打开", async () => {
    await page.click('[data-view="jobs"]');
    await page.waitForSelector("[data-open-job]", { timeout: 10000 });
    await page.locator("[data-open-job]").first().click();
    await page.waitForSelector("#scanView:not(.hidden)");
    await expectText(page, "#resultSubtitle", "fixed_shift_demo.csv");
  });

  await browser.close();
  console.log("论文科研数据筛查｜真实场景用语版 HTML 交互验证");
  for (const [name, status] of results) console.log(`${status}  ${name}`);
  console.log(`SUMMARY  ${results.length - failures.length}/${results.length} passed`);
  if (failures.length) process.exitCode = 1;
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
