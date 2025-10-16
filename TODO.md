# 入库数据流水线 TODO

## 后端流程概览（1→Merge, 2→Clean, 3→Filter, 4→Update）
- **Merge** (`backend/src/merge/data_merge.py:25`): 读取 `data/raw/<topic>/<date>/*.xlsx`，按渠道字段配置合并 Excel，去重后写入 `data/merge/<topic>/<date>/<channel>.xlsx`。
- **Clean** (`backend/src/clean/data_clean.py:105`): 按渠道映射标准列名，拼接文本为 `contents`，规范地域与时间格式，重排 `id` 并二次去重，输出 `data/clean/<topic>/<date>/<channel>.xlsx`。
- **Filter** (`backend/src/filter/data_filter.py:130`): 裁剪 `contents`，组合提示词调用千问模型，解析响应中的相关性与分类，仅保留高相关记录，写入 `data/filter/<topic>/<date>/<channel>.xlsx`。
- **Update** (`backend/src/update/data_update.py:69`): 确保数据库与标准表结构存在，对 `data/filter/<topic>/<date>` 中的 Excel 去重后批量 `to_sql` 入库（一个文件对应一张表）。

## 前端调用串联
- **推荐调用**：`POST /api/pipeline`，后端顺序执行 Merge → Clean → Filter → Upload，响应体中的 `steps` 数组给出每一步的 `success` 状态与返回值。
- **备用拆分**：如需逐步调试，可继续依次调用 `POST /api/merge → /api/clean → /api/filter → /api/upload`，请求体统一为 `{ topic: string, date: "YYYY-MM-DD" }`。
- **请求节奏**：Pipeline 为同步阻塞调用，Filter 步骤耗时最长；前端需在调用期间展示 Loading/进度提示，必要时可结合日志流或轮询刷新。
- **成功判断**：管道接口返回 `{"status":"ok","steps":[...]}` 表示全流程完成；若任何步骤失败，`status="error"` 且 `steps` 中标记出失败节点，前端应提取 `message` 给用户，并提供重新尝试或局部重跑入口。

## 待办事项
- [ ] 在前端新增 `/api/pipeline` 一键入库入口，利用 `steps` 结果渲染实时状态与异常提示。
- [ ] 保留手动四步调用作为高级调试模式，并提示用户核对 `configs/prompt/filter/<topic>.yaml` 是否存在。
- [ ] 联合后端确认生产环境数据库连接与权限配置（`config.yaml.databases`）已验证可写。
