# Capability Map

本表把 `ability_ledger`、canonical tool registry 和 skill contract 收敛成同一张运行图。

| ability_id | artifact / outcome | runtime owner | backing tools | backing skills |
|---|---|---|---|---|
| `runtime.task_orchestration` | structured payload / interrupt payload / runtime diagnostic | `report_coordinator` | — | `sentiment-analysis-methodology` |
| `evidence.normalize_retrieve_verify` | `NormalizedTaskResult` / `EvidenceCardPage` / `CorpusCoverageResult` / `ClaimVerificationPage` | `report_coordinator`, `retrieval_router`, `archive_evidence_organizer`, `validator` | `normalize_task`, `get_corpus_coverage`, `retrieve_evidence_cards`, `verify_claim_v2`, `get_basic_analysis_snapshot` | `retrieval-router-rules`, `evidence-source-credibility`, `quality-validation-backlink` |
| `semantic.report_ir_assembly` | `ReportIR` / `ArtifactManifest` | `report_coordinator` | — | — |
| `semantic.agenda_frame_builder` | `AgendaFrameMap` | `report_coordinator`, `agenda_frame_builder` | `build_agenda_frame_map` | — |
| `semantic.conflict_map_builder` | `ConflictMap` | `report_coordinator`, `stance_conflict`, `claim_actor_conflict` | `extract_actor_positions`, `build_claim_actor_conflict` | `subject-stance-merging` |
| `semantic.mechanism_builder` | `MechanismSummary` / `RiskSignalResult` | `report_coordinator`, `timeline_analyst`, `propagation_analyst` | `build_event_timeline`, `compute_report_metrics`, `build_mechanism_summary`, `detect_risk_signals`, `build_basic_analysis_insight` | `timeline-alignment-slicing`, `propagation-explanation-framework`, `chart-interpretation-guidelines` |
| `semantic.utility_gate` | `UtilityAssessment` | `report_coordinator`, `decision_utility_judge` | `judge_decision_utility` | `quality-validation-backlink` |
| `semantic.evidence_semantic_enrichment` | claim matrix / section evidence packs / snapshot-derived insights | `report_coordinator`, `bertopic_evolution_analyst` | `get_basic_analysis_snapshot`, `build_basic_analysis_insight`, `get_bertopic_snapshot`, `build_bertopic_insight`, `build_section_packet`, methodology/reference tools | `basic-analysis-framework`, `bertopic-evolution-framework`, `sentiment-analysis-methodology` |
| `compat.structured_generation` | legacy structured payload / report cache | `report_agent` compat surface | legacy analysis tools in `report/tools` | — |
| `compiler.full_markdown_compile` | markdown / full payload | compiler graph or future plain writer surface | — | `report-writing-framework`, `chart-interpretation-guidelines` |
| `compiler.scene_layout_critic_graph` | layout plan / section budgets / final markdown | compiler graph or future plain writer surface | — | `report-writing-framework` |

规则：

- judgment artifact 的生命周期归 capability / workflow / subagent 所有，不归某个单独 tool 所有。
- `report/tools` 只注册 shared LangChain tools；runtime surface 与 skill attachment 一律从 capability contract 投影。
- guidance-only skills 不能脱离 capability/runtime/agent family 自动挂到 specialist 上。
