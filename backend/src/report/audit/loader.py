from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .schema import (
    AbilityLedger,
    AgentPassRefactor,
    AuditBundle,
    ReportIRMapping,
    RuntimeBoundaryAudit,
    SkillEvalPlan,
)


_AUDIT_DIR = Path(__file__).resolve().parent


def _load_json(name: str) -> Dict[str, Any]:
    path = _AUDIT_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload if isinstance(payload, dict) else {}


def load_ability_ledger() -> AbilityLedger:
    return AbilityLedger.model_validate(_load_json("ability_ledger.json"))


def load_runtime_boundary_audit() -> RuntimeBoundaryAudit:
    return RuntimeBoundaryAudit.model_validate(_load_json("runtime_boundary_audit.json"))


def load_report_ir_mapping() -> ReportIRMapping:
    return ReportIRMapping.model_validate(_load_json("report_ir_mapping.json"))


def load_agent_pass_refactor() -> AgentPassRefactor:
    return AgentPassRefactor.model_validate(_load_json("agent_pass_refactor.json"))


def load_skill_eval_plan() -> SkillEvalPlan:
    return SkillEvalPlan.model_validate(_load_json("skill_eval_plan.json"))


def load_audit_bundle() -> AuditBundle:
    docs = {
        "artifact_lineage_map": str((_AUDIT_DIR / "artifact_lineage_map.md").resolve()),
        "capability_map": str((_AUDIT_DIR / "capability_map.md").resolve()),
        "frontend_workspace_convergence": str((_AUDIT_DIR / "frontend_workspace_convergence.md").resolve()),
        "method_contracts": str((_AUDIT_DIR / "method_contracts.md").resolve()),
        "release_gate": str((_AUDIT_DIR / "release_gate.md").resolve()),
        "legacy_retirement_map": str((_AUDIT_DIR / "legacy_retirement_map.json").resolve()),
        "runtime_surface_alignment": str((_AUDIT_DIR / "runtime_surface_alignment.md").resolve()),
        "smoke_scenarios": str((_AUDIT_DIR / "smoke_scenarios.md").resolve()),
        "tool_authoring_standard": str((_AUDIT_DIR / "tool_authoring_standard.md").resolve()),
        "tool_migration_backlog": str((_AUDIT_DIR / "tool_migration_backlog.json").resolve()),
        "readme": str((_AUDIT_DIR / "README.md").resolve()),
    }
    return AuditBundle(
        ability_ledger=load_ability_ledger(),
        runtime_boundary_audit=load_runtime_boundary_audit(),
        report_ir_mapping=load_report_ir_mapping(),
        agent_pass_refactor=load_agent_pass_refactor(),
        skill_eval_plan=load_skill_eval_plan(),
        docs=docs,
    )
