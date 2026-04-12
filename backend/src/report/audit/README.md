# Report Audit Assets

本目录存放“Ability Ledger 优先”的迁移审查资产，用于把报告系统从文件/路由视角，改写成能力、边界、lineage 和 system-of-record 视角。

真实任务调试入口：

- 先看 [runtime_surface_alignment.md](/f:/opinion-system/backend/src/report/audit/runtime_surface_alignment.md)，确认当前只认 `thread_id + artifact_manifest + approvals + lineage` 这套 runtime truth。
- 再看 [smoke_scenarios.md](/f:/opinion-system/backend/src/report/audit/smoke_scenarios.md)，按 Happy Path、Semantic Review、Fallback Recompile、Resume After Failure 四条路径做最小运行验证。
- 若任务进入 review 或 fallback，优先检查 `artifact manifest`、`approval records`、`fallback_trace` 和同一 `thread_id` 上的 lineage 追加，而不是回退到 topic/date 推断。
- 真实任务排障时，先看三层位点：graph（阶段 / router / dispatch / interrupt / resume）、artifact（lineage / policy / review / fallback）、decision（utility / review delta / fallback trace / 放行原因）。
- cleanup 删除顺序只看 [legacy_retirement_map.json](/f:/opinion-system/backend/src/report/audit/legacy_retirement_map.json) 的 `delete_order` 和 `blocking_smoke`，不按文件手感删。

当前资产：

- `ability_ledger.json`
  当前能力台账。按运行时、证据、语义、编译、视图、兼容层分组，记录输入、输出、LLM/tool 使用、状态写入、失败形态和质量责任。
- `runtime_boundary_audit.json`
  runtime boundary 审查。区分哪些对象必须留在 runtime 内，哪些对象必须 snapshot 化。
- `report_ir_mapping.json`
  现有 structured payload 到 `ReportIR` 的映射表，标记 direct / restructure / projection / drop。
- `agent_pass_refactor.json`
  agent 与 deterministic compiler pass 的拆分方案。
- `skill_eval_plan.json`
  skill-level eval 与 system regression 计划。
- `artifact_lineage_map.md`
  从输入到缓存再到前端消费的 lineage 审查与收敛目标。
- `frontend_workspace_convergence.md`
  前端从三页心智收敛到单 task/thread 工作台的方案。
- `analysis_object_completeness_ledger.json`
  检查 `AgendaFrameMap`、`ConflictMap`、`MechanismSummary`、`UtilityAssessment` 是否具备对象、证据、边界、可用性。
- `analysis_method_ledger.json`
  记录每个 judgment artifact 对应的方法变量、子图结构和理论来源，确保系统按方法主线推进，而不是按字段堆叠推进。
- `specialist_quality_ledger.json`
  跟踪 agenda/frame、conflict、mechanism、utility specialists 的输入质量、误差类型与改进重点。
- `trace_grading_ledger.json`
  跟踪 `router -> agenda/frame -> conflict -> mechanism -> utility gate -> review` 全链路中的回退与失效类型。
- `typed_boundary_ledger.json`
  记录仍在消费 raw dict / prose / legacy payload 的路径，以及计划替换的 typed schema。
- `lineage_completeness_ledger.json`
  检查新 judgment artifacts 是否具备 parent refs、policy version、approval records、thread/run ids。
- `legacy_residual_ledger.json`
  只记录 residual logic 还保留哪些独占分析能力，以及何时才能彻底退役。
- `capability_map.md`
  把 ability、runtime owner、backing tools 与 backing skills 收敛到一张能力图。
- `tool_authoring_standard.md`
  规定 LangGraph / Deep Agents 共享 tool 的统一写法与边界。
- `tool_migration_backlog.json`
  记录当前 tools / skills / runtime projection 的 aligned / partial / redesign 状态。
- `method_contracts.md`
  冻结四个方法对象和四个 specialist 的语义职责、输入输出、禁止越界和 trace grading 维度。
- `release_gate.md`
  定义进入下一轮 cleanup 前必须满足的对象完整性 gate、specialist 质量 gate 和 utility/review gate。
- `legacy_retirement_map.json`
  记录 legacy 当前残余的独占能力、主链调用方、替代者以及是否具备 cleanup 条件。
- `runtime_surface_alignment.md`
  固定前后端共享的 canonical runtime surface，以及 topic/date 与 thread/artifact 的职责边界。
- `smoke_scenarios.md`
  固定 cleanup 前必须通过的四条运行级 smoke 场景，用于真实任务前的运行面验收。
- `framework_alignment_checklist.md`
  对照 LangGraph / Deep Agents 官方能力，逐项评定当前主链的对齐状态（已对齐 / 部分对齐 / 未对齐），含代码级实证与修复建议。

使用原则：

- 这些文件是迁移审查的 system notes，不是运行时配置。
- 任何 service 拆分、能力迁移、兼容层删除，都要先更新这里的台账与边界说明。
- 方法论升级同样要先更新这里的对象台账、method ledger 与 eval 计划，再进入实现。
- 收尾阶段必须先更新 `method_contracts.md`、`release_gate.md` 和 `legacy_retirement_map.json`，再进入 cleanup。
- 规整阶段必须先更新 `runtime_surface_alignment.md` 与 `smoke_scenarios.md`，再进入前后端联调和 smoke 补测。
- 如果代码已经改变而审查资产未更新，默认以审查资产失效处理，需要先补齐。

规整阶段的最小执行顺序：

1. 先看 `runtime_surface_alignment.md`，确认当前 task/thread/runtime surface 的唯一真相面。
2. 再跑 `smoke_scenarios.md` 中的四条 smoke，确认 happy/review/fallback/resume 四条主路径都可回放。
3. 如果真实任务需要排障，优先看 task thread、artifact manifest、approval records 和 lineage，而不是从 topic/date 反推当前结果。
4. `legacy_retirement_map.json` 只用于下一轮按顺序删除 legacy，不用于本轮新增兼容入口。

cleanup 删除波次：

1. 第一波只断 import、registry 和 compat wrapper，不删 legacy 文件本体。
2. 第二波只删 `legacy_retirement_map.json` 中 `cleanup_ready=true` 且 `still_imported=false` 的实现。
3. 第三波再做目录和命名统一；这一步不能与删除波次混做。

当前 cleanup 状态：

- `full_report_service`、`structured_service` 已删除并由 guard test 保护。
- `runtime.py` compat bridge 已删除；主链只保留 `runtime_bootstrap.py` 作为 analyze/explain bootstrap 归属点。
- runtime 退役后的回归继续由 Happy Path 与 Resume After Failure 两条 blocking smoke 保护。
- 审批机制已从旧的 `semantic_review_markdown` 路径全面切换为 `graph_interrupt`；  
  `approvals[].tool_name = "graph_interrupt"`，resume 三要素为 `interrupt_id + checkpoint_locator + graph_thread_id`，  
  详见 `runtime_surface_alignment.md` 的 **Approval / Interrupt 字段结构** 小节。

长期维护拓扑：

- `report/runtime`
  只承载 task、thread、approval、manifest、resume 和 bootstrap。
- `report/deep_report/analysis`
  只承载 judgment artifact builders、semantic control 和 specialist glue。
- `report/deep_report/compiler`
  只承载 section plan、draft bundle、rewrite、conformance。
- `report/deep_report/presentation`
  只承载 presenter 与 final markdown projection。
- `report/audit`
  只承载 contracts、release gate、retirement、smoke 与 loader。

当前若暂未做物理拆目录，也必须按这五类职责维护 import 方向，避免 runtime、analysis、compiler、presentation 再次混写。

执行环境说明：

- Windows 前端测试如果在受限沙箱里触发 `spawn EPERM`，按执行环境权限问题记录。
- 这类问题需要在 smoke 或测试说明中保留，但不作为 runtime contract 变更依据。
