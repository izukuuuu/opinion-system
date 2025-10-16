# 入库数据流水线 TODO

## 后端流程概览（1→Merge, 2→Clean, 3→Filter, 4→Update）
- **Merge** (`backend/src/merge/data_merge.py:25`): 读取 `backend/data/projects/<topic>/raw/<date>/*.xlsx`，按渠道配置合并 Sheet，并输出 `backend/data/projects/<topic>/merge/<date>/<channel>.jsonl`。
- **Clean** (`backend/src/clean/data_clean.py:105`): 对 JSONL 渠道数据做字段映射、文本拼接、地域与时间规范化，生成 `backend/data/projects/<topic>/clean/<date>/<channel>.jsonl`。
- **Filter** (`backend/src/filter/data_filter.py:130`): 读取 clean 产物裁剪内容、调用千问模型判定相关性，仅保留高相关记录并写回 `backend/data/projects/<topic>/filter/<date>/<channel>.jsonl`。
- **Update** (`backend/src/update/data_update.py:69`): 遍历 filter JSONL，清洗去重后按渠道写入数据库中的 `{topic}.{channel}` 表。

## 前端调用串联
- **执行顺序**：前端应依次调用 `POST /api/merge → /api/clean → /api/filter → /api/upload`，每个接口共用 `{ topic: string, date: "YYYY-MM-DD" }` 请求体；上一步失败时立刻终止并提示。
- **状态反馈**：每个接口返回 `{"status":"ok","operation": "...", "data": ...}` 代表成功；遇到 `status:"error"` 需弹出 `message` 并允许用户重试当前步骤。
- **进度提示**：Merge/Clean 主要是本地 I/O，可直接 await；Filter 依赖 LLM，时延较高，需展示 Loading；Upload 触发前应再次确认 Filter 成功，以免写入空数据。
- **补充能力**：`POST /api/pipeline` 仍保留作为后端串行执行的备用方案（调试或脚本化场景），响应包含 `steps` 明细，可用于后台作业或二次排障。

## 待办事项
- [ ] 将四个接口串联进前端的入库流程（按钮/向导均可），并在 Filter 步骤加入可视化进度提示。
- [ ] 调用 Filter 前先校验 `configs/prompt/filter/<topic>.yaml` 是否存在；缺失时提醒用户补充提示词或跳过筛选。
- [ ] 与后端同步新的文件布局与 JSONL 规范，确保部署环境已创建 `backend/data/projects/<topic>/raw` 等目录并拥有写权限。
