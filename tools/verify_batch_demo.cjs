const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

// Run against a disposable server and runtime so verification cannot add user history.
const baseUrl = process.env.DEMO_URL;
if (!baseUrl || new URL(baseUrl).port === "8765") {
  throw new Error("请设置 DEMO_URL 为独立验收服务地址，不能使用日常演示端口 8765。");
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const results = [];
  const sample = fs.readFileSync(path.resolve("mvp-demo/samples/fixed_shift_demo.csv"));
  const file = (name, buffer = sample) => ({ name, mimeType: "text/csv", buffer });
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  async function text(selector, expected) {
    assert((await page.locator(selector).innerText()).includes(expected), `${selector} 未显示：${expected}`);
  }
  async function check(name, task) {
    try { await task(); results.push([name, "PASS"]); }
    catch (error) { results.push([name, `FAIL：${error.message}`]); }
  }
  async function clearFiles() { if (await page.locator("#clearBtn").isVisible()) await page.click("#clearBtn"); }
  async function scan() {
    await page.waitForFunction(() => !document.getElementById("scanBtn").disabled);
    const submitted = page.waitForResponse(response => response.url().endsWith("/api/jobs") && response.request().method() === "POST");
    await page.click("#scanBtn");
    assert(await page.locator("#chooseBtn").isDisabled(), "检查期间仍允许更改材料");
    assert(await page.locator("#clearBtn").isDisabled(), "检查期间仍允许清空材料");
    const accepted = await (await submitted).json();
    assert(accepted.ok, accepted.error || "任务未创建");
    await page.waitForSelector("#resultView:not(.hidden)", { timeout: 190000 });
    const stored = await (await context.request.get(`${baseUrl.replace(/\/$/, "")}/api/jobs/${accepted.job.job_id}`)).json();
    return stored.job;
  }
  await page.goto(baseUrl, { waitUntil: "networkidle" });

  await check("多次选择和拖拽追加，逐项移除", async () => {
    await page.setInputFiles("#fileInput", file("正文.csv"));
    await page.setInputFiles("#fileInput", file("补充.csv"));
    assert(await page.locator("[data-remove-file]").count() === 2, "第二次选择覆盖了第一次选择");
    const transfer = await page.evaluateHandle(() => {
      const data = new DataTransfer();
      data.items.add(new File(["value\n0.2\n0.3\n"], "原始记录.csv", { type: "text/csv" }));
      return data;
    });
    await page.dispatchEvent("#dropZone", "drop", { dataTransfer: transfer });
    await transfer.dispose();
    assert(await page.locator("[data-remove-file]").count() === 3, "拖拽未追加材料");
    await page.getByRole("button", { name: "移除 补充.csv", exact: true }).click();
    assert(await page.locator("[data-remove-file]").count() === 2, "逐项移除未生效");
    await text("#fileList", "正文.csv");
    await text("#fileList", "原始记录.csv");
  });

  await check("重复文件、格式、单文件大小与数量限制", async () => {
    await clearFiles();
    await page.setInputFiles("#fileInput", file("Data.csv"));
    await page.setInputFiles("#fileInput", file("data.CSV"));
    await text("#scanError", "重名");
    assert(await page.locator("[data-remove-file]").count() === 1, "重名材料被加入");
    await page.setInputFiles("#fileInput", file("readme.txt"));
    await text("#scanError", "暂不支持");
    await page.setInputFiles("#fileInput", file("large.csv", Buffer.alloc(20 * 1048576 + 1, "1")));
    await text("#scanError", "超过 20 MB");
    await clearFiles();
    await page.setInputFiles("#fileInput", Array.from({ length: 21 }, (_, i) => file(`data-${i}.csv`)));
    await text("#scanError", "最多同时提交 20 份");
    assert(await page.locator("[data-remove-file]").count() === 0, "超量文件被部分静默接受");
  });

  let batchJob;
  await check("两份真实材料一起筛查并显示读取情况", async () => {
    await page.setInputFiles("#fileInput", [file("正文.csv"), file("补充.csv")]);
    batchJob = await scan();
    assert(batchJob.file_count === 2, "任务未记录两份材料");
    await text("#statFiles", "2");
    await text("#materialsSummary", "2 / 2");
    await page.locator("#materialsSummary").click();
    await text("#materialsList", "正文.csv");
    await text("#materialsList", "补充.csv");
  });

  await check("跨材料线索展示两侧原始数值与位置", async () => {
    assert(batchJob, "前一项未得到批量结果");
    const finding = batchJob.result.findings.find(item => (item.evidence?.comparison || []).some(pair => pair.left.file !== pair.right.file));
    assert(finding, "两份相同数据没有得到跨材料对照线索");
    await page.locator(`[data-finding="${finding.id}"]`).click();
    const pair = finding.evidence.comparison[0];
    for (const cell of [pair.left, pair.right]) {
      await text("#evidenceTable", cell.file);
      await text("#evidenceTable", `第 ${cell.row_idx} 行`);
      await text("#evidenceTable", String(cell.value));
    }
    await text("#evidenceTable", "第一组原始数值");
    if (process.env.BATCH_SCREENSHOT) await page.screenshot({ path: process.env.BATCH_SCREENSHOT, fullPage: true });
  });

  await check("记录列表无需完整结果，可重新打开批量记录", async () => {
    const listing = await (await context.request.get(`${baseUrl.replace(/\/$/, "")}/api/jobs`)).json();
    assert(listing.jobs.every(job => !Object.hasOwn(job, "result")), "列表仍传输完整结果");
    await page.click('[data-view="jobs"]');
    await text("#jobsView", "重新启动后仍可查看");
    await page.locator(`[data-open-job="${batchJob.job_id}"]`).click();
    await page.waitForSelector("#resultView:not(.hidden)");
    await text("#statFiles", "2");
    await text("#materialsSummary", "2 / 2");
  });

  await check("部分材料无法读取时明确显示未覆盖内容", async () => {
    await clearFiles();
    await page.setInputFiles("#fileInput", [file("原始数据.csv"), file("损坏附件.pdf", Buffer.from("not a valid PDF"))]);
    const mixed = await scan();
    assert(mixed.result.coverage_summary.status !== "complete", "损坏附件仍标记完整检查");
    assert(await page.locator("#coverageNotice").isVisible(), "未展示未读取范围提示");
    await text("#materialsList", "损坏附件.pdf");
    assert(mixed.result.materials.some(material => material.status !== "read"), "材料读取状态遗漏失败附件");
  });

  await check("无数据可读时不显示无异常，报告可下载", async () => {
    await clearFiles();
    await page.setInputFiles("#fileInput", file("损坏材料.pdf", Buffer.from("not a valid PDF")));
    const unread = await scan();
    assert(unread.result.coverage_summary.status !== "complete", "全部失败仍标记完整检查");
    const summary = await page.locator("#summary").innerText();
    assert(!summary.includes("未发现需要核对的数据"), "未读数据仍宣称没有异常");
    await text("#summary", "未检查的内容仍需另行核对");
    const [download] = await Promise.all([page.waitForEvent("download"), page.click("#exportBtn")]);
    assert(download.suggestedFilename().endsWith("-筛查报告.html"), "下载报告扩展名不正确");
  });

  results.push(["浏览器脚本无未处理错误", errors.length ? `FAIL：${errors.join("；")}` : "PASS"]);
  await browser.close();
  for (const [name, status] of results) console.log(`${status}  ${name}`);
  const passed = results.filter(([, status]) => status === "PASS").length;
  console.log(`SUMMARY ${passed}/${results.length} passed`);
  if (passed !== results.length) process.exitCode = 1;
}

run().catch(error => { console.error(error); process.exitCode = 1; });
