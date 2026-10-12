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

本轮回归：后端 **186/186**、交付包浏览器 **8/8**、AI 浏览器（Mock）**4/4**，四组件合成样例实际运行均成功。原 32 项规范提示的逐项处理见[本地交付范围验收](docs/product/12_佰茵云本地交付验收.md)。

## 佰茵云目录交付

开发源码和构建入口均纳入版本管理；运行结果及生成的交付包留本机。Windows 仓库根目录执行：

```powershell
python -m pip install -r mvp-demo/requirements.txt -r tools/requirements-build.txt
python tools/build_delivery.py
```

在 `delivery/PaperAudit-时间戳/` 生成 Coding、Agent、AgentRun、AgentOM 四个同级组件及等内容的 Word/HTML/Markdown 说明。Coding 内仅有 `Code/Data/TempData/Result`；运行批处理入口 `python Code/PaperAudit.py`。交互工作台入口为 Agent 内的 `python harness/Workbench.py`，管理员可用 `PAPER_AUDIT_PORT` 设置本机端口。批处理读取材料及三项可选参数，不自动调用模型；DOI 和逐条费用确认通过工作台完成。

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

主要 API：`GET /api/health`；`POST /api/jobs`、`GET /api/jobs[/{id}]`；`POST /api/materials/discover`、`/api/materials/import`；`GET /artifact/{scan}/result.json`、`/scan.json`、`/report.html`；`GET /api/explanations/{scan}/{finding}`、`POST /api/explanations/quote`、`/api/explanations/run`；`GET /api/reviews/{scan}`、`POST /api/reviews`、`/api/reports`。操作步骤见[使用教程](docs/product/03_使用教程.md)。

## 数据安全与边界

本地服务只监听回环地址；上传文件、SQLite、扫描产物和模型用量记录位于忽略提交的 `runtime/`。请勿把真实论文材料、运行目录、密钥或报告产物推送到公开仓库。模型输出是可追溯的辅助说明，不会修改 PaperConan 检测结果或人工复核决定。PDF 图片/扫描件不做 OCR；导入的公开页面可能因站点限制失败；高密度 100 MB 数据尚未通过容量验收。真实模型已在内置合成样例上完成一次逐条解释及页面读取测试；**真实论文解释质量、跨类型稳定性和实际账单仍未验收**。

佰茵云账户认证、租户隔离、平台存储、任务调度、部署和联调由平台方后续完成，见[接入清单](docs/product/09_平台接入清单.md)。本地账号不是平台身份，不能直接对外网开放。

第三方：PaperConan 0.8.5（MIT）为扫描依赖，DeepSeek 为外部付费 API；其他 Python 依赖及许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。未把 PaperConan 上游源码复制进仓库。历史材料的移动、缓存清理和未移动项见[目录整理清单](docs/product/11_目录整理清单.md)。
