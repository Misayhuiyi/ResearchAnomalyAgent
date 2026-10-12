# 第三方组件与许可

本仓库调用固定版本依赖，不复制或修改下列上游源码。下表基于本地已安装包的元数据；实际再分发时仍须核对各依赖及其传递依赖的完整许可文本。

| 组件 | 版本 | 用途 | 许可 |
| --- | --- | --- | --- |
| [PaperConan](https://github.com/zixixr/paperconan/blob/main/LICENSE) | 0.8.5 | 科研数据解析与确定性扫描 | MIT |
| [openpyxl](https://openpyxl.readthedocs.io/) | 3.1.5 | Excel 读取 | MIT |
| [SciPy](https://scipy.org/) | 1.17.1 | 数值计算 | BSD 系列；二进制包可能另带 OpenBLAS 许可 |
| [python-docx](https://python-docx.readthedocs.io/) | 1.2.0 | Word 报告 | MIT |
| [ReportLab](https://www.reportlab.com/) | 4.4.9 | PDF 报告 | BSD 系列 |
| [pypdf](https://pypdf.readthedocs.io/) | 6.10.0 | PDF 文本读取 | BSD-3-Clause |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 0.11.9 | PDF 表格读取 | MIT |
| [psutil](https://github.com/giampaolo/psutil) | 7.2.2 | 本机任务资源监测 | BSD-3-Clause |

DeepSeek 是可选外部 API 服务，不是随仓库再分发的开源组件；使用者需自行遵守其服务条款和计费规则。工作流模板保留在 `.agents/` 等目录，其原有许可不由本项目重许可。论文原文、公开数据和第三方推文仅用于本地验收或调研，不作为本仓库的通用可再分发素材。
