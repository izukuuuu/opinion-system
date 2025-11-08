# AI API 调用与配置说明

本文档梳理项目中大模型调用的整体结构，包括后端客户端实现、Token 统计方式、配置文件约定以及前端的模型来源切换。适用于在阿里通义千问（DashScope）与 OpenAI 兼容接口之间切换或并行接入的场景。

## 1. 调用流程总览
- **筛选流（Filter）**：`backend/src/filter/data_filter.py` 中的 `run_filter_async` 会读取 `configs/llm.yaml` 内的 `filter_llm` 配置，根据 `provider` 初始化对应的客户端并发起异步调用。
- **对话/助手流（Assistant）**：前端提供独立配置，后端可按相同方式扩展，实现与筛选流相同的客户端复用。
- 两条流的核心差异仅在于 `provider`、`model` 等参数，代码层面通过统一的客户端接口和 Token 统计辅助函数来适配。

## 2. 环境变量与依赖
| 功能 | 必需环境变量 | 说明 |
| ---- | ------------ | ---- |
| 通义千问 API | `DASHSCOPE_API_KEY` | `backend/src/utils/setting/env_loader.py` 的 `get_api_key` 会读取此值，无需改动。 |
| OpenAI 兼容 API | `OPENAI_API_KEY` 或 `OPINION_OPENAI_API_KEY` | 用于 `OpenAIClient`；如果需要自建或代理服务，可额外设置 `OPENAI_BASE_URL`/`OPINION_OPENAI_BASE_URL`。 |

新增依赖清单已写入 `backend/requirements.txt`：
- `openai>=1.14.0`：官方 SDK，使用异步 `AsyncOpenAI` 客户端。
- `tiktoken>=0.5.2`：用于 OpenAI Token 估算，缺失时会自动退化为字符长度估算。

## 3. 后端客户端实现
### 3.1 通义千问：`backend/src/utils/ai/qwen.py`
- `QwenClient.call(prompt, model, max_tokens)` 通过 DashScope REST 接口发起请求。
- 默认超时、连接池等参数已配置，返回值统一为 `{"text": "...", "usage": {...}}`。

### 3.2 OpenAI 兼容接口：`backend/src/utils/ai/openai_client.py`
- 新增 `OpenAIClient`，懒加载获取 API Key 与可选的 Base URL。
- 使用 `AsyncOpenAI.chat.completions.create`，保持与 QwenClient 一致的返回结构。
- 若缺少 `openai` 依赖或环境变量未配置，会抛出明确的异常以便运维排错。

### 3.3 客户端调度：`backend/src/filter/data_filter.py`
- 根据 `filter_llm.provider` 选择 `QwenClient` 或 `OpenAIClient`。
- QPS、批量等参数逻辑保持原状；使用 `count_tokens` 作为 Token 统计兜底，避免不同 Provider 的字段差异带来统计缺失。

## 4. Token 统计：`backend/src/utils/ai/token.py`
- `count_tokens(prompt, model, provider)` 会根据 Provider 分派至 Qwen（DashScope 官方 tokenizer）或 OpenAI（tiktoken）。
- `estimate_total_tokens(prompt, completion, model, provider)` 可在接口未返回使用信息时提供估算值，统一结构为 `input_tokens`、`output_tokens`、`total_tokens`。

## 5. 配置文件：`backend/configs/llm.yaml`
```yaml
filter_llm:
  # provider 可选值：qwen（阿里通义千问）或 openai（OpenAI 兼容接口）
  provider: "qwen"
  model: "qwen-plus"
  qps: 50
  batch_size: 32
  truncation: 200
```
- `provider` 目前支持 `qwen` 与 `openai`；后续扩展到其他兼容服务时，只需新增对应客户端并在 `data_filter` 中调度即可。
- 其他字段保持通用语义（模型名、QPS、单批数量、截断长度）。

## 6. 前端配置入口：`frontend/src/views/SettingsView.vue`
- “筛选模型配置” 与 “对话模型配置” 两个表单使用下拉框明确区分 `阿里通义千问` 与 `OpenAI/兼容 API`。
- `provider` 字段默认值为 `qwen`，成功读取后端配置时若缺失会自动回落到该默认值。
- 根据当前 Provider 动态更新模型输入框的占位提示（如 `gpt-3.5-turbo`、`qwen-plus`），减少误填概率。
- 新增 “API 密钥配置” 卡片可直接写入/清空 DashScope 与 OpenAI API Key，并在同一处维护 `OPENAI_BASE_URL`。成功保存后端会落盘到 `configs/llm.yaml` 的 `credentials` 字段，`env_loader` 会自动优先读取该值。

## 7. 集成建议
1. **测试流程**：在切换 Provider 前，确认 `.env` 中已经配置对应的 API Key，并运行一遍 `python backend/server.py` 或相关脚本验证调用。
2. **日志观察**：`backend/logs/` 中的筛选日志会记录 Provider 与模型信息，便于排查调用来源。
3. **后续扩展**：若需要为对话流添加 OpenAI 支持，可重用 `OpenAIClient`，并在相应方法中引入 `count_tokens` 作为兜底统计。

如需进一步扩展（例如流式响应、函数调用等），建议以该文档中的客户端封装为起点，确保不同 Provider 共享一致的接口定义与错误处理逻辑。
