# Artifact Lineage Map

## Current Lineage

当前链路并不是单一 truth-source，而是混合了 task state、cache 文件、legacy bootstrap 与页面回退逻辑：

1. 输入进入 `api.py`
   - 同步读取 `/api/report`、`/api/report/full`
   - 异步创建 `/api/report/tasks`
2. `worker.py` 读取 queued task
   - 先调用 `runtime_bootstrap.py` 做 analyze / explain bootstrap
   - 再进入 `deep_report.run_or_resume_deep_report_task()`
3. `deep_report`
   - 生成 structured payload
   - 组装 `ReportIR` 与 `ArtifactManifest`
   - 生成 full markdown payload
4. 持久化产物
   - `report_payload.json`
   - `report_ir.json`
   - `ai_full_report_payload.json`
   - runtime artifact / workspace state files
5. 前端消费
   - 运行台优先读 task snapshot + stream events
   - 语义报告页读 structured payload
   - 正式文稿页读 full payload
   - 某些回退分支仍允许按 topic/date 猜测结果

## Duplicate Generation Points

当前需要重点盯住的重复生成点：

- `runtime_bootstrap.py` 仍会在 task 之前补 analyze / explain 结果
- 同步接口与异步任务都可能触发 structured/full cache 重建
- legacy progress 逻辑仍会直接根据 cache 和日志目录反推状态
- 前端运行页仍允许在无 task 产物时，只凭 topic/date 打开结果页

## Current Risks

- `report_payload.json` 与 `ai_full_report_payload.json` 仍承担了部分 system-of-record 角色
- task state 与 cache payload 里仍同时存在 digest、manifest 与历史快照，需继续避免重复表达状态
- `thread_id` 已出现，但页面和部分兼容逻辑还没有强制以其为唯一上下文

## Target Lineage

收敛后的唯一原则：

1. `task_id / thread_id` 是唯一运行时主键
2. `artifact_manifest` 是唯一产物目录
3. `ReportIR` 是唯一语义真相源
4. `structured_projection` 与 `full_markdown` 都是 artifact projection
5. 页面只消费同一 thread 下的 artifacts，不再按 topic/date 猜状态

## De-duplication Checklist

- 禁止同步入口绕过 `task/thread + artifact manifest` 直产最终 truth source
- 禁止 legacy progress 再把 cache/log 当作主状态源
- 禁止页面重新引入 `report_ready/full_report_ready` 这类布尔门
- 所有 artifact 版本变化都必须能在 task event 流和 manifest 中回溯
