# Frontend Workspace Convergence

## Current State Sources

当前前端已经开始接入：

- `threadId`
- `artifactManifest`
- `reportIrSummary`
- `structuredResultDigest`

当前主视图已经不再把 `report_ready/full_report_ready` 当作状态门，也不再用 topic/date 推断结果页可达性。

## Canonical State Model

统一后的前端状态源只保留以下主字段：

- `canonicalTaskId`
- `canonicalThreadId`
- `artifactManifest`
- `reportIrSummary`
- `currentRun`
- `currentStructuredArtifact`
- `currentFullArtifact`
- `activeView`

兼容字段的地位：

- `structuredResultDigest`
  退化为 `reportIrSummary` 的兼容镜像

## View Rules

三视图统一规则：

- 运行台：只显示当前 task/thread 的生命周期、events、approvals、latest artifacts
- 语义报告：只显示当前 task/thread 下 `structured_projection`
- 正式文稿：只显示当前 task/thread 下 `full_markdown`

不得继续存在的行为：

- 运行台用 topic/date 猜“结果页是否可打开”
- 语义报告页与正式文稿页各自重新推断一份“当前结果”
- 三页分别定义不同的成功判定

## Route Convergence Target

短期：

- 保留三个路由
- 三个路由共用一个 store 和同一 task/thread

中期：

- 合并为一个 workspace 容器
- 路由只切 `activeView`

长期：

- 用户只面对一个任务中心
- artifact inspector 与 approvals 成为右侧固定面板

## Concrete Audit Points

迁移时必须逐条检查：

- 哪些 view model 仍混用 digest 与 manifest
- 哪些按钮仍仅基于 topic/date 开放
- 哪些页面在 task 缺失时会自行拉取 cache 并建立“伪当前状态”
