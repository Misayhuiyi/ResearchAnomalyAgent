# 论文科研数据异常筛查 Agent

本项目帮助研究人员核对论文及随附数据中的异常数值关系。PaperConan 负责可复现的计算，DeepSeek V4.1 Flash 仅对单条已发现线索给出中文辅助解释，用户依据原始材料自行复核。**统计信号不是科研不端结论，也不能判断作者意图。**

当前交付是 Windows 本机独立运行版本，不是纯静态 HTML，也未接入佰茵云账号、存储或部署。界面沿用既有 [HTML UI](prototypes/论文科研数据异常筛查Agent_UI.html) 的简洁工作台结构。

## 已实现

- 上传 CSV、TSV、XLSX、XLS、XLSM、XLSB、文字型 PDF、DOCX；校验文件名、格式、大小和重名。一次最多 20 份，每份 20 MB，合计 100 MB；具体可处理量还受 1 GiB 引擎内存和 180 秒时限约束。
- 支持快速（Triage）、标准（Review）、全面（Forensic）三种策略，调用 PaperConan 0.8.5 做真实扫描；固定平移、固定比例、精确线性、重复、舍入和尾数等线索以实际可读材料为准。
- 展示文件、工作表、数据块、数值单元格、覆盖/未覆盖状态、优先级、数量、数学关系、原始行列和完整数值；支持搜索、筛选、初筛 HTML/JSON 下载与 PaperConan 原始记录查看。
- 支持 DOI/公开论文链接候选导入（不绕过登录或付费）、后台任务、取消、历史记录、人工复核与冻结的 Word/PDF/Excel/HTML 报告。
- 可选逐条 AI 解释：先显示保守费用上限并由用户确认；只发送线索摘要和最多 3 组/4 个原始数值样本，不发送完整论文或数据文件。解释绑定检查记录、线索及证据摘要；AI 失败不影响原扫描。
- 内置 35 行合成样例：`treated = control + 0.3`，`scaled = control × 2`。样例验证工程逻辑，不代表真实论文质量评估。

流程：**上传或选择公开材料 → 创建扫描 → 查看覆盖范围和异常线索 → 核对原始证据 → 可选 AI 解释 → 保存复核并导出。**

## 本地安装和启动

需要 Windows 10/11、Python 3.11+、PowerShell 和联网安装依赖。根目录执行：

```powershell
cd mvp-demo
.\setup.ps1
.\start.ps1
```

浏览器打开 `http://127.0.0.1:8765/`，点击“载入示例文件”再“开始筛查”。不要把 `static/index.html` 单独发给别人：真实计算与保存依赖本机 Python 服务。若已有服务占用 8765，可在 `mvp-demo` 目录运行 `.\.venv\Scripts\python.exe app.py --port 8878`，再访问对应端口。

## DeepSeek 配置与费用

官方模型展示名称为 **DeepSeek-V4.1-Flash**，API model ID 为 **`deepseek-flash`**；默认地址为 `https://api.deepseek.com`。见[官方模型列表](https://api-docs.deepseek.com/api/list-models/)和[定价页](https://api-docs.deepseek.com/quick_start/pricing/)。

优先读取环境变量 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。可参考 [.env.example](.env.example)，但程序**不会自动加载 `.env`**；在当前 PowerShell 会话设置变量，或运行 `python tools/configure_local_model.py` 通过隐藏输入和 Windows 当前用户加密保存。后者的配置只留在 `%LOCALAPPDATA%`，不进仓库。无密钥时扫描、人工复核和导出仍可用，逐条 AI 解释会明确提示未配置。模型地址和标识固定校验为官方值，防止误将材料发送到其他地址。

费用按官方峰时、未命中缓存的价格作保守预估；每条线索单独确认。已发出的超时请求不会自动重试以避免重复计费；明确被 HTTP 429 拒绝的请求最多再试一次。价格核验期为 2026-11-11 UTC，过期后须重新核对定价，不能静默继续付费。API 密钥不得填入页面、提交到 Git 或发送给他人。此前在聊天中披露过的密钥建议轮换。

## 测试

```powershell
cd mvp-demo
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -q
```

浏览器验收脚本位于 `tools/`，必须对隔离的测试端口运行；`tools/serve_ai_mock.py` 和 `tools/verify_ai_browser.cjs` 只使用 Mock 模型，绝不调用付费接口。最新实测数量、真实 API 冒烟和未覆盖风险见[测试验收报告](docs/product/08_测试验收报告.md)。

修复后验证共255项通过，含后端210项、12案页面流程、12案原值核对、8案Mock解释和1次失败隔离、2案参考版本核对、10条此前真实回复导出检查。各项范围及历史失败记录见[修复验收](docs/product/14_问题修复与版本核对验收.md)。本次重新打包的独立验证见[最新交付记录](docs/product/15_V2.4交付与发布记录.md)，不把Mock或旧回复计作新的真实调用。

## 佰茵云目录交付

开发源码和构建入口均纳入版本管理；运行结果及生成的交付包留本机。Windows 仓库根目录执行：

```powershell
python -m pip install -r mvp-demo/requirements.txt -r tools/requirements-build.txt
python tools/build_delivery.py
```

在 `delivery/PaperAudit-时间戳/` 生成 Coding、Agent、AgentRun、AgentOM 四个同级组件及等内容的 Word/HTML/Markdown 说明；最新V2.4蓝图、教程及接入说明在Coding/Data/ProductDocs。Coding 内仅有 `Code/Data/TempData/Result`；运行批处理入口 `python Code/PaperAudit.py`。交互工作台入口为 Agent 内的 `python harness/Workbench.py`，管理员可用 `PAPER_AUDIT_PORT` 设置本机端口。批处理读取材料及三项可选参数，不自动调用模型；DOI、参考版本核对和逐条费用确认通过工作台完成。

Word更新由 `tools/update_product_docs.py` 从保留的V2.3版式及现行教程内容生成V2.4，不覆盖原件。打包与文档构建需要 `tools/requirements-build.txt`；生成包、真实论文、运行数据和密钥都不上传GitHub，仓库只保留可复现构建源码及文档。

## 目录与接口

```text
mvp-demo/          本地服务、扫描/证据/模型/费用模块、页面、样例和测试
docs/product/       建设蓝图、教程、UI 对照、调研、接入和验收文档
docs/specs/         需求与边界合同
tools/              构建、配置和隔离验收脚本
delivery-src/       四组件交付入口和输入检查源码
prototypes/         历史 UI 参考；运行页面以 mvp-demo/static 为准
.agents/            原工作流模板及按需加载技能
```

主要 API：`GET /api/health`；`POST /api/jobs`、`GET /api/jobs[/{id}]`；`POST /api/materials/discover`、`/api/materials/import`；`GET /artifact/{scan}/result.json`、`/scan.json`、`/report.html`；`GET /api/explanations/{scan}/{finding}`、`POST /api/explanations/quote`、`/api/explanations/run`；`GET /api/reviews/{scan}`、`POST /api/reviews`、`/api/reports`；`POST /api/reference/preview`、`/api/reference/compare`和`GET /api/reference/{scan}`。操作步骤见[使用教程](docs/product/03_使用教程.md)和[建设蓝图V2.4](docs/product/02_论文科研数据异常筛查Agent建设蓝图_V2.4.docx)。

## 多论文测试集

本机 `test-corpus/测试集导航.html` 保留 5 篇真实论文、原版/修正版及人工对照，共 12 个可直接上传的案例。双击同目录 `打开检查工具.cmd` 可打开工具和导航。修复后记录在 `test-results/2026-10-11-fixes-final/`；此前真实模型回复及新生成的含解释报告在 `test-results/2026-10-11-multipaper-v1/`。原材料与模型响应不公开提交。

准备：`python tools/prepare_paper_corpus.py`。免费重跑：`python tools/run_paper_corpus.py --node node --port 8897`（需要 Playwright/Chromium，可用 `--node-modules` 指定包目录）。不会调用付费模型，结果不覆盖旧轮次。

新增“与参考版本核对”：明确选择原表/参考表、工作表、匹配编号和核对列；没有唯一编号时需确认数据顺序一致。Iris 的 3 处差异及运动实验 K6 的 1 处差异均完成真实核对、导出和重开验证。单靠统计扫描仍不保证识别孤立错误；参考版本也不自动视为正确。编号数列不再列为测量异常；PDF 区分文字可读、表格未读和加密/扫描边界。已保存 AI 解释会合入新生成的四格式报告，旧报告不改写。详见[修复验收](docs/product/14_问题修复与版本核对验收.md)，历史证据见[原测试集记录](docs/product/13_多论文测试集与验收记录.md)。

## 数据安全与边界

本地服务只监听回环地址；上传文件、SQLite、扫描产物和模型用量记录位于忽略提交的 `runtime/` 或本机 `test-results/`。请勿把真实论文材料、运行目录、密钥或报告产物推送到公开仓库。模型输出和参考版本核对都是可追溯的辅助说明，不会修改 PaperConan 检测结果或人工复核决定。版本核对支持 CSV、TSV、XLSX、XLSM；单参考文件20MB、一轮最多20份/100MB，解析最多20万单元格；不能唯一匹配、公式无缓存或超出范围时明确拒绝/标部分，不强行比较。PDF 图片/扫描件不做 OCR，不解密；区间复合文字不当作原始观测扫描。高密度 100 MB 全量扫描容量、领域模型质量、随机稳定性和真实账单仍未验收。

佰茵云账户认证、租户隔离、平台存储、任务调度、部署和联调由平台方后续完成，见[接入清单](docs/product/09_平台接入清单.md)。本地账号不是平台身份，不能直接对外网开放。

第三方：PaperConan 0.8.5（MIT）为扫描依赖，DeepSeek 为外部付费 API；其他 Python 依赖及许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。未把 PaperConan 上游源码复制进仓库。历史材料的移动、缓存清理和未移动项见[目录整理清单](docs/product/11_目录整理清单.md)。
