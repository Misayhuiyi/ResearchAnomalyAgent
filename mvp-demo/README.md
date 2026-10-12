# 本地运行目录

完整功能、启动方法、API、边界和测试记录以[仓库根 README](../README.md)为准。此目录包含 Python 本地服务、PaperConan 扫描适配、DeepSeek 调用与费用账本、前端工作台、样例和测试。

在本目录执行 `./setup.ps1` 安装并运行测试，再执行 `./start.ps1`，访问 `http://127.0.0.1:8765/`。Windows PowerShell 中也可用 `& .\.venv\Scripts\python.exe app.py --port 8878` 指定其他本机端口。

运行产物保存在 `runtime/`，不应上传到公开仓库。AI 可选；无密钥时仍能完成扫描、原值核对、人工复核和报告导出。[模型设置](MODEL-SETUP.md)单独说明。
