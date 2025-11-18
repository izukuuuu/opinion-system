# 内容编码分析（ContentAnalyze）集成说明

本模块提供“基于大模型的新闻内容编码分析”，核心实现位于 `backend/src/contentanalyze/data_contentanalyze.py`。当前唯一入口是 CLI 命令 `ContentAnalyze`，内部会读取抓取到的新闻数据，调用千问 Qwen 模型完成多维度编码，并输出 Excel 详情和 JSON 统计。要将其接入前端，可按下列说明理解依赖、输入输出路径与可复用的调用方式。

## 处理流程与输入
- 数据来源：默认读取 `backend/data/fetch/{topic}/{start}_{end}/新闻.csv`。文件不存在时会在同目录内回退查找包含“新闻/news”的 CSV。
- 必需字段：正文列名需命中 `contents`、`文段`、`正文`、`内容` 之一（按顺序匹配）。缺失则直接报错并返回失败。
- 批处理：使用 `llm.content_analysis_llm.batch_size`（默认 32）分批，按 `qps`（默认 50）节流，单次请求超时 60s。
- 调用 LLM：拼接 `system_prompt` + `analysis_prompt`（见下方提示词配置），向 DashScope 文本生成接口发送请求，解析返回内容中的 JSON 片段。
- 动态字段：根据模型返回的字段自动推断单/多选并汇总所有出现的字段；Excel 及统计 JSON 会包含全集字段。

## 产出
- Excel 明细：`backend/data/contentanalyze/{topic}/{start}_{end}/contentanalysis.xlsx`，含原文、状态和模型返回的所有字段列。
- JSON 统计：`backend/data/contentanalyze/{topic}/{start}_{end}/contentanalysis.json`，仅包含字段分布与类型（single_select / multi_select）。
- 运行日志：写入 `backend/logs/{topic}/{start}_{end}/` 下的对应日志文件。

## 配置项
- 提示词：`configs/prompt/contentanalysis/{topic}.yaml`。若无同名文件，则使用该目录下第一个 YAML。文件需至少包含 `system_prompt` 与 `analysis_prompt`。
- 模型参数：从 `settings.get('llm.content_analysis_llm', {})` 读取，缺省值 `model=qwen-plus, qps=50, batch_size=32`。实际配置来源可放在 `configs/llm.yaml` 或运行时 `settings/llm.yaml`。
- API 凭据：通过运行时设置文件 `settings/llm.yaml` 中的 `credentials.qwen_api_key|dashscope_api_key` 提供。前端 `/settings/ai` 页面调用 `/api/settings/llm/credentials` 即可写入同一位置，因此无需额外新增配置项。

## 现有调用方式（CLI）
```bash
cd backend
python main.py ContentAnalyze --topic 控烟 --start 2025-01-01 --end 2025-01-31
```
前置条件：已完成对应专题的 Fetch 流程，确保 `backend/data/fetch/控烟/2025-01-01_2025-01-31/新闻.csv` 存在且包含正文列。

## 前端/后端集成建议
当前没有 HTTP 接口，前端无法直接触发 ContentAnalyze。可复用 `run_content_analysis_sync(topic, start_date, end_date)` 作为后端入口，在 `backend/server.py` 中新增类似 `analyze` 的接口，例如：
1) `POST /api/content/analyze`，body `{ topic|project|dataset_id, start, end }`；解析参数可复用 `prepare_pipeline_args`/`resolve_topic_identifier`。
2) 在后台线程执行 `run_content_analysis_sync` 以避免阻塞请求；执行前校验 `fetch` 产物是否存在。
3) 成功后返回产出文件的相对路径或下载用的短链接；需要的话再补一个静态下载/预览接口读取 `contentanalysis.xlsx` 与 `contentanalysis.json`。

## 前端 AI 配置（/settings/ai）检查要点
- Vue 页面 `frontend/src/views/settings/SettingsAiView.vue` 已包含 DashScope 与 OpenAI 的 API Key、Base URL 表单，背后调用 `/api/settings/llm` 与 `/api/settings/llm/credentials`。
- ContentAnalyze 仅需 DashScope Key；在页面中填入“DashScope API Key”后保存即可写入 `settings/llm.yaml`，`get_api_key()` 会自动读取，无需新增字段。
- 若需要为内容分析单独调整 `model/qps/batch_size`，可在运行时配置文件 `settings/llm.yaml` 下新增 `content_analysis_llm` 段，前端可复用现有表单或追加编辑区域。
