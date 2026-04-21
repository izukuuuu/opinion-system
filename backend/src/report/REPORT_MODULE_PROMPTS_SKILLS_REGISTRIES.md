# Report Module Prompt / Skill / Registry 索引

这份文档描述 `backend/src/report/` 下当前仍在生效的 prompt、skills、registry 与 compat 入口。

目标不是讲抽象设计，而是回答下面几个维护问题：

- 现在有哪些 prompt 在跑
- 这些 prompt 分别在哪个 runtime 路径生效
- skills 从哪里发现、如何校验、如何挂到 agent / subagent 上
- 当前有哪些 registry，谁是“可执行真源”，谁只是“投影 / 合同层”
- 遇到一个 agent / skill / tool / artifact 问题时，应该先看哪个文件

## 1. 先看整体分层

`report` 模块里和 prompt / skill / registry 相关的核心层次如下：

| 层 | 主要文件 | 作用 | 是否主链真源 |
|---|---|---|---|
| Prompt 模板层 | `structured_prompts.py` | 结构化 JSON 生成、scene/layout/budget/critic/revise 等 prompt builder | 是，但只对对应调用链生效 |
| Deep Report subagent prompt 层 | `deep_report/builder.py` | coordinator 与每个 subagent 的长 `system_prompt` | 是，Deep Report 主链真源 |
| Plain/Agent runtime prompt 层 | `agent_runtime.py` | plain / analysis runner 的 runtime system prompt 与 skill catalog prompt | 是，但不属于 Deep Report 主链 |
| Skill 资产层 | `skills/loader.py`、`skills/*/SKILL.md` | skill 发现、解析、标准化、资源索引、能力/工具校验 | 是 |
| Subagent 元数据层 | `configs/subagents.yaml` | tier、description、skill_keys、output_files/output_globs | 是 |
| Subagent 派生 registry | `deep_report/subagent_registry.py` | 从 YAML 派生 tier / required artifacts / repair tiers / prompt 排序等 | 是，Deep Report 主链元数据真源 |
| Tool 可执行 registry | `tools/registry.py` | canonical tool catalog、runtime tool 选择、skill tool id 校验 | 是，工具真源 |
| Capability / Skill 合同层 | `capability_manifest.py` | capability、runtime surface、skill contract、投影关系 | 是，但偏合同/投影，不直接执行 |
| Compat 收口层 | `deep_report/compat.py` | legacy interrupt、`payload_json` 兼容入口 | 是，但只承接兼容路径 |

如果你只想排查 Deep Report 主链，优先按下面顺序读：

1. `deep_report/service.py`
2. `deep_report/builder.py`
3. `deep_report/subagent_registry.py`
4. `configs/subagents.yaml`
5. `tools/registry.py`
6. `skills/loader.py`
7. `capability_manifest.py`

## 2. Prompt 现状

### 2.1 Deep Report 主链 prompt

Deep Report 主链 prompt 主要分三类：

1. `deep_report/builder.py`
   - coordinator `system_prompt`
   - coordinator 初始 user prompt
   - 每个 subagent 的长 `system_prompt`
   - 这是当前 Deep Report 主链最重要的一组 prompt
   - prompt 文本仍写死在代码里，没有迁入 YAML

2. `deep_report/service.py`
   - `_call_writer_markdown()` 的 system prompt
   - `_invoke_document_composer()` 的 system prompt
   - 这些 prompt 不是 subagent prompt，而是 compile / render 辅助 prompt

3. `deep_report/deep_writer.py`、`deep_report/semantic_control.py`
   - 章节写作 prompt
   - trace 抽取器 prompt
   - 语义状态抽取 prompt
   - 这些属于 compile / document / semantic control 路径

### 2.2 结构化 prompt builder

`structured_prompts.py` 是另一套 prompt builder，主要给结构化 JSON 产物服务。当前仍然有效的 builder 包括：

- `build_section_agent_system_prompt`
- `build_section_agent_analysis_prompt`
- `build_title_subtitle_prompt`
- `build_stage_notes_prompt`
- `build_insights_prompt`
- `build_bertopic_insight_prompt`
- `build_bertopic_temporal_narrative_prompt`
- `build_interpretation_prompt`
- `build_full_report_scene_prompt`
- `build_full_report_layout_prompt`
- `build_full_report_budget_prompt`
- `build_full_report_mechanism_prompt`
- `build_full_report_risk_map_prompt`
- `build_full_report_brief_prompt`
- `build_full_report_section_prompt`
- `build_full_report_style_critic_prompt`
- `build_full_report_fact_critic_prompt`
- `build_full_report_markdown_prompt`
- `build_full_report_revise_prompt`

这套 prompt 的特点：

- 默认要求输出严格 JSON
- 明显偏“结构化生成 / compile 辅助”
- 和 `deep_report/builder.py` 的 subagent prompt 不是一回事

### 2.3 Plain / analysis runtime prompt

`agent_runtime.py` 下还有一套运行时 prompt，主要服务 plain runtime 和老的 section/analysis runner：

- `_build_skill_catalog_prompt()`
- `_compose_runtime_system_prompt()`
- `_build_plain_load_skill_tool()`
- `create_analysis_agent_runner()` 等调用点里内联的短 system prompt

这里的 prompt 重点不是 Deep Report 多 subagent 主链，而是：

- 给普通 `create_agent(...)` runner 提供上下文
- 在 plain fallback 路径里暴露 skill catalog
- 用 `load_skill` 工具按需加载 SKILL.md

### 2.4 运行时补写 / fallback prompt

以下 prompt 仍然存在，但不属于主链真源：

- `runtime_bootstrap.py`
  - 为缺失 explain 产物补写文本
- `deep_report/service.py`
  - 文档编排和 markdown 渲染辅助 prompt

这些应视为补写/辅助 prompt，不要误认为 Deep Report subagent 规范。

## 3. Skills 现状

### 3.1 Skill 真源在哪里

当前 skill 真源是：

- `backend/src/report/skills/*/SKILL.md`
- `backend/src/report/skills/loader.py`

`skills/README.md` 说明的是规范，不是执行器。

loader 当前负责：

- 发现技能目录
- 解析 `SKILL.md` frontmatter 与正文
- 读取 `references/`、`assets/` 等资源索引
- 标准化 alias / display name / documentType
- 校验 `allowed_tools`
- 校验 `capabilityIds`、`runtimeSurfaces`、`agentFamilies`
- 在运行时生成 catalog、resolved skill、staged files

### 3.2 当前内置 skill 列表

当前 `backend/src/report/skills/` 下的内置 skill 目录有：

- `agenda-frame-builder`
- `basic-analysis-framework`
- `bertopic-evolution-framework`
- `chart-interpretation-guidelines`
- `evidence-source-credibility`
- `formal-report-factual-style`
- `media-analysis-framework`
- `propagation-explanation-framework`
- `quality-validation-backlink`
- `report-writing-framework`
- `retrieval-router-rules`
- `sentiment-analysis-methodology`
- `subject-stance-merging`
- `timeline-alignment-slicing`

### 3.3 Skills 如何挂到 Deep Report 主链

Deep Report 主链下，skill 挂载流程是：

1. `configs/subagents.yaml`
   - 声明 `coordinator.skill_keys`
   - 声明每个 subagent 的 `skill_keys`

2. `deep_report/subagent_registry.py`
   - 读取 YAML skill keys
   - 调 `select_report_skill_sources(...)`
   - 结合 runtime target / agent_name / available tools 选择最终 skill sources

3. `deep_report/builder.py`
   - 将最终 `skills` 传给 Deep Agents `create_deep_agent(...)`

当前 YAML 中的 skill 绑定关系如下：

| Agent | skill_keys |
|---|---|
| `report_coordinator` | `basic-analysis-framework`, `sentiment-analysis-methodology` |
| `retrieval_router` | `retrieval-router-rules` |
| `archive_evidence_organizer` | `evidence-source-credibility` |
| `bertopic_evolution_analyst` | `bertopic-evolution-framework` |
| `timeline_analyst` | `timeline-alignment-slicing` |
| `stance_conflict` | `subject-stance-merging`, `media-analysis-framework` |
| `event_analyst` | `sentiment-analysis-methodology`, `propagation-explanation-framework` |
| `claim_actor_conflict` | `subject-stance-merging` |
| `agenda_frame_builder` | `agenda-frame-builder` |
| `propagation_analyst` | `propagation-explanation-framework`, `chart-interpretation-guidelines`, `media-analysis-framework` |
| `decision_utility_judge` | `quality-validation-backlink` |
| `writer` | `formal-report-factual-style`, `report-writing-framework`, `sentiment-analysis-methodology`, `chart-interpretation-guidelines`, `propagation-explanation-framework` |

### 3.4 Skills 如何挂到 plain runtime

plain runtime 不直接吃 Deep Agents skill attachment，而是：

- `agent_runtime.py` 在 prompt 里暴露 skill catalog
- 通过 `load_skill` 工具按需读取完整 `SKILL.md`
- `build_report_skill_runtime_assets(...)` 负责把 skill 资源 staged 进 runtime

这也是为什么当前 skills 有两条用法：

- Deep runtime：直接 `skills=[...]`
- Plain runtime：catalog + `load_skill`

## 4. Registry 现状

### 4.1 `tools/registry.py`：唯一可执行工具真源

这个文件是 report 模块下最重要的 executable registry。

它定义了：

- `_TOOL_SPECS`
- `ReportToolSpec`
- `get_report_tool_catalog()`
- `get_report_tool_spec()`
- `select_report_tools()`
- `validate_skill_tool_ids()`
- `SUBAGENT_TOOL_ID_MAP`
- `DEEP_REPORT_COORDINATOR_TOOL_IDS`
- `SECTION_TOOL_NAME_MAP`
- `ANALYSIS_AGENT_TOOL_ID_MAP`

应当把它理解为：

- 工具能不能执行，看这里
- 某个 runtime surface 能拿到哪些工具，看这里
- skill 的 `allowed_tools` 合不合法，看这里

### 4.2 `capability_manifest.py`：合同 / 投影层

这个文件不是直接执行工具，但它定义了能力合同和 skill contract：

- `ReportCapabilitySpec`
- `ReportSkillContract`
- `select_runtime_capability_ids()`
- `select_runtime_tool_ids()`
- `select_runtime_skill_ids()`
- `get_skill_capability_ids()`
- `get_skill_runtime_surfaces()`
- `get_skill_agent_families()`
- `is_guidance_only_skill()`

当前 runtime surface 常量包括：

- `RUNTIME_AGENT`
- `RUNTIME_COORDINATOR`
- `RUNTIME_SUBAGENT`
- `RUNTIME_PLAIN_COMPAT`
- `RUNTIME_MANUAL_ONLY`

应当把它理解为：

- 定义“理论上某个 runtime / agent family / capability 允许什么”
- 但最终真正执行工具，仍以 `tools/registry.py` 为准

### 4.3 `deep_report/subagent_registry.py`：Deep Report 主链派生层

这个文件是这轮收敛后新增的主链派生 registry。

它从：

- `configs/subagents.yaml`
- `tools/registry.py`
- `skills/*`

派生出 Deep Report 主链真正使用的元数据，包括：

- `SUPPORTED_SUBAGENT_NAMES`
- `build_tier_prompt_lines()`
- `build_tier_todo_specs()`
- `build_runtime_subagent_specs()`
- `build_subagent_spec_map()`
- `build_coordinator_skills()`
- `get_repair_agent_tiers()`
- `get_exploration_artifact_owners()`
- `get_required_exploration_artifacts()`

应当把它理解为：

- `subagents.yaml` 的 runtime 解释器
- Deep Report 主链下 tier / output / repair / artifact owner 的唯一派生层

### 4.4 `configs/subagents.yaml`：Deep Report 元数据真源

YAML 当前只负责声明式元数据，不负责复杂执行逻辑。

它当前负责：

- `tier`
- `description`
- `skill_keys`
- `output_files`
- `output_globs`

它当前不负责：

- `system_prompt`
- tools 绑定
- middleware
- Deep Agents 实例化

### 4.5 现在不要再把这些东西搞混

一个实用记法：

- “能不能执行某个工具”看 `tools/registry.py`
- “某个 skill 合法挂给谁”看 `capability_manifest.py` + `skills/loader.py`
- “Deep Report 主链具体 tier / outputs / repair 怎么派生”看 `subagent_registry.py`
- “Deep Report subagent 到底说什么 prompt”看 `deep_report/builder.py`

## 5. Deep Report 主链当前接线

### 5.1 主链入口

主链入口是：

- `worker.py` -> `deep_report/service.py` -> `run_or_resume_deep_report_task(...)`

### 5.2 主链 runtime 分层

主链现在分 4 层：

1. Root orchestrator graph
   - `deep_report/orchestrator_graph.py`
   - 只负责 `planning -> exploration -> compile`

2. Exploration deterministic graph
   - `deep_report/exploration_deterministic_graph.py`
   - 只负责 tier 调度、readiness、repair、finalize

3. Deep agent builder
   - `deep_report/builder.py`
   - 只负责 coordinator/subagent Deep Agents 实例化

4. Compat facade
   - `deep_report/compat.py`
   - 只承接 legacy interrupt 和 `payload_json` 兼容

### 5.3 现在 Deep Report 主链里谁决定什么

| 信息 | 真源 |
|---|---|
| subagent tier / outputs / skill_keys | `configs/subagents.yaml` |
| Deep Report tier prompt 展示 / repair tiers / required artifacts / owners | `deep_report/subagent_registry.py` |
| subagent tools | `tools/registry.py` 的 `SUBAGENT_TOOL_ID_MAP` + `select_report_tools()` |
| subagent system prompt | `deep_report/builder.py` |
| coordinator prompt | `deep_report/builder.py` |
| structured compile prompt | `structured_prompts.py` |
| skill 解析与校验 | `skills/loader.py` |

## 6. 兼容层现状

当前已显式收口、仍然保留的 compat 入口有：

- `deep_report/compat.py`
  - `extract_legacy_interrupts()`
  - `parse_structured_report_tool_input()`

它们当前承接的旧行为是：

- `__interrupt__` legacy interrupt 读取
- `save_structured_report(payload_json=...)` 旧 JSON 入口

仍然在模块里存在、但不属于 Deep Report 主链真源的 fallback / 兼容路径有：

- `agent_runtime.py` 的 plain compat 路径
- `runtime_bootstrap.py` 的 explain 补写
- `data_report.py` 的旧报告链路与 prompt yaml

这些路径不应与当前 Deep Report 主链混读。

## 7. 常见维护问题怎么定位

### 7.1 “某个 subagent 为什么没产出某个文件？”

按这个顺序看：

1. `configs/subagents.yaml`
2. `deep_report/subagent_registry.py`
3. `deep_report/exploration_deterministic_graph.py`
4. `deep_report/service.py`

### 7.2 “某个 skill 为什么没挂上？”

按这个顺序看：

1. `configs/subagents.yaml` 的 `skill_keys`
2. `skills/loader.py` 的解析与 `allowed_tools`
3. `capability_manifest.py` 的 runtime surface / agent family / capability contract
4. `deep_report/subagent_registry.py` 的 `build_runtime_subagent_specs()`

### 7.3 “某个 tool 为什么这里能用，那里不能用？”

按这个顺序看：

1. `tools/registry.py` 的 `_TOOL_SPECS`
2. `tools/registry.py` 的 `select_report_tools()`
3. `capability_manifest.py` 的 `select_runtime_tool_ids()`
4. 对 skill 还要额外看 `validate_skill_tool_ids()`

### 7.4 “某个 prompt 到底是哪条链路在用？”

快速定位：

- Deep Report subagent / coordinator：`deep_report/builder.py`
- compile / structured JSON：`structured_prompts.py`
- plain/analysis runner：`agent_runtime.py`
- explain 补写：`runtime_bootstrap.py`
- document composer / markdown render：`deep_report/service.py`
- deep writer / semantic control：`deep_report/deep_writer.py`、`deep_report/semantic_control.py`

## 8. 当前最容易误解的点

### 8.1 `subagents.yaml` 不是 prompt 真源

它是元数据真源，不是 subagent prompt 真源。

### 8.2 `capability_manifest.py` 不是工具执行真源

它是 capability / skill contract 和 runtime projection 层，不直接实例化工具。

### 8.3 `skills/README.md` 不是 skill 执行真源

执行真源是 `skills/loader.py` + 各个 `SKILL.md`。

### 8.4 `structured_prompts.py` 不是 Deep Report subagent prompt 文件

它是另一套结构化生成 / compile prompt builder。

## 9. 推荐阅读顺序

第一次接手 `report` 模块，建议按下面顺序读：

1. 本文档
2. `skills/README.md`
3. `configs/subagents.yaml`
4. `deep_report/subagent_registry.py`
5. `tools/registry.py`
6. `capability_manifest.py`
7. `deep_report/builder.py`
8. `deep_report/exploration_deterministic_graph.py`
9. `deep_report/service.py`
10. `structured_prompts.py`
11. `agent_runtime.py`

如果你已经在改 Deep Report 主链，就尽量不要从 `data_report.py` 开始读，那是旧链。
