# DeepSeek 接入与费用

请以根目录 [DeepSeek 接入说明](../docs/product/07_DeepSeek接入说明.md) 为准。

本机首选在当前 PowerShell 会话设置 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。也可在交互终端运行 `python tools/configure_local_model.py`，隐藏输入并用 Windows 当前用户 DPAPI 保存至仓库外。不要把密钥写入 `.env`、源码、聊天或 Git。

模型 API 标识为 `deepseek-flash`，展示名称为 DeepSeek-V4.1-Flash。调用之前逐条显示保守费用上限；用户确认才发送最小证据。价格核验期截至 2026-11-11 UTC，实际账单以服务方为准。模型故障不会抹掉确定性扫描；超时请求不自动重发。
