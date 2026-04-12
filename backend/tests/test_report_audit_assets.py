from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.audit.loader import (
    load_ability_ledger,
    load_agent_pass_refactor,
    load_audit_bundle,
    load_report_ir_mapping,
    load_runtime_boundary_audit,
    load_skill_eval_plan,
)


class ReportAuditAssetsTests(unittest.TestCase):
    def test_ability_ledger_covers_required_modules_and_layers(self) -> None:
        ledger = load_ability_ledger()
        self.assertIn("deep_report", ledger.modules)
        self.assertIn("full_report_service", ledger.modules)
        self.assertIn("structured_service", ledger.modules)
        self.assertIn("runtime", ledger.modules)
        self.assertIn("api", ledger.modules)
        self.assertIn("worker", ledger.modules)
        layers = {entry.layer for entry in ledger.abilities}
        self.assertEqual(
            layers,
            {"runtime", "evidence", "semantic", "compiler", "view", "compat"},
        )
        ids = {entry.ability_id for entry in ledger.abilities}
        self.assertIn("semantic.report_ir_assembly", ids)
        self.assertIn("view.frontend_workspace_projection", ids)

    def test_runtime_boundary_audit_keeps_snapshot_contracts_explicit(self) -> None:
        audit = load_runtime_boundary_audit()
        self.assertIn("artifact manifest", audit.must_snapshot)
        self.assertIn("ReportIR", audit.must_snapshot)
        self.assertTrue(any("schema family" in rule for rule in audit.rules))
        self.assertTrue(any("legacy progress" in risk for risk in audit.current_boundary_risks))

    def test_report_ir_mapping_preserves_projection_vs_truth_source(self) -> None:
        mapping = load_report_ir_mapping()
        projection_sources = {entry.source_field for entry in mapping.projection}
        self.assertIn("report_document", projection_sources)
        self.assertIn("markdown", projection_sources)
        direct_sources = {entry.source_field for entry in mapping.direct}
        self.assertIn("timeline", direct_sources)
        restructure_sources = {entry.source_field for entry in mapping.restructure}
        self.assertIn("key_evidence", restructure_sources)

    def test_agent_pass_refactor_distinguishes_agent_pass_and_compat(self) -> None:
        refactor = load_agent_pass_refactor()
        keep_ids = {entry.ability for entry in refactor.keep_as_agent}
        pass_ids = {entry.ability for entry in refactor.convert_to_pass}
        compat_ids = {entry.ability for entry in refactor.freeze_as_compat}
        self.assertIn("planner/router", keep_ids)
        self.assertIn("markdown compiler", pass_ids)
        self.assertIn("legacy structured report generation", compat_ids)
        self.assertTrue(all(entry.target_shape == "agent" for entry in refactor.keep_as_agent))
        self.assertTrue(all(entry.target_shape == "pass" for entry in refactor.convert_to_pass))
        self.assertTrue(all(entry.target_shape == "freeze" for entry in refactor.freeze_as_compat))

    def test_skill_eval_plan_covers_required_skill_and_system_regressions(self) -> None:
        plan = load_skill_eval_plan()
        skill_ids = {entry.skill_id for entry in plan.skill_evals}
        regression_ids = {entry.skill_id for entry in plan.system_regressions}
        self.assertIn("agenda-frame-coherence", skill_ids)
        self.assertIn("actor-alias-collapse", skill_ids)
        self.assertIn("claim-evidence-traceability", skill_ids)
        self.assertIn("full-markdown-no-new-facts", skill_ids)
        self.assertIn("conflict-graph-quality", skill_ids)
        self.assertIn("mechanism-traceability", skill_ids)
        self.assertIn("mechanism-synthesis-fault", skill_ids)
        self.assertIn("decision-utility-usefulness", skill_ids)
        self.assertIn("routing-fault", skill_ids)
        self.assertIn("frame-synthesis-fault", skill_ids)
        self.assertIn("conflict-synthesis-fault", skill_ids)
        self.assertIn("utility-gate-fault", skill_ids)
        self.assertIn("runtime-contract", regression_ids)
        self.assertIn("frontend-contract", regression_ids)

    def test_audit_bundle_references_human_docs(self) -> None:
        bundle = load_audit_bundle()
        self.assertTrue(bundle.docs["artifact_lineage_map"].endswith("artifact_lineage_map.md"))
        self.assertTrue(bundle.docs["frontend_workspace_convergence"].endswith("frontend_workspace_convergence.md"))
        self.assertTrue(bundle.docs["method_contracts"].endswith("method_contracts.md"))
        self.assertTrue(bundle.docs["release_gate"].endswith("release_gate.md"))
        self.assertTrue(bundle.docs["legacy_retirement_map"].endswith("legacy_retirement_map.json"))
        self.assertTrue(bundle.docs["runtime_surface_alignment"].endswith("runtime_surface_alignment.md"))
        self.assertTrue(bundle.docs["smoke_scenarios"].endswith("smoke_scenarios.md"))
        self.assertTrue(Path(bundle.docs["readme"]).exists())

    def test_analysis_ledgers_exist_and_are_documented(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "report" / "audit"
        expected = {
            "analysis_method_ledger.json",
            "analysis_object_completeness_ledger.json",
            "specialist_quality_ledger.json",
            "trace_grading_ledger.json",
            "typed_boundary_ledger.json",
            "lineage_completeness_ledger.json",
            "legacy_residual_ledger.json",
            "method_contracts.md",
            "release_gate.md",
            "legacy_retirement_map.json",
            "runtime_surface_alignment.md",
            "smoke_scenarios.md",
        }
        self.assertTrue(expected.issubset({path.name for path in root.iterdir()}))
        readme = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("analysis_method_ledger.json", readme)
        self.assertIn("analysis_object_completeness_ledger.json", readme)
        self.assertIn("specialist_quality_ledger.json", readme)
        self.assertIn("trace_grading_ledger.json", readme)
        self.assertIn("method_contracts.md", readme)
        self.assertIn("release_gate.md", readme)
        self.assertIn("legacy_retirement_map.json", readme)
        self.assertIn("runtime_surface_alignment.md", readme)
        self.assertIn("smoke_scenarios.md", readme)
        legacy_residual = json.loads((root / "legacy_residual_ledger.json").read_text(encoding="utf-8"))
        residual_by_module = {
            entry["module"]: entry["status"]
            for entry in legacy_residual.get("residual_logic", [])
            if isinstance(entry, dict)
        }
        self.assertEqual(residual_by_module.get("full_report_service"), "retired")
        self.assertEqual(residual_by_module.get("structured_service"), "retired")
        self.assertEqual(residual_by_module.get("runtime"), "retired")
        self.assertIn("delete_order", readme)
        self.assertIn("blocking_smoke", readme)

    def test_method_contracts_and_release_gate_freeze_next_round_scope(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "report" / "audit"
        contracts = (root / "method_contracts.md").read_text(encoding="utf-8")
        self.assertIn("AgendaFrameMap", contracts)
        self.assertIn("ConflictMap", contracts)
        self.assertIn("MechanismSummary", contracts)
        self.assertIn("UtilityAssessment", contracts)
        self.assertIn("agenda_frame_builder", contracts)
        self.assertIn("propagation_analyst", contracts)
        self.assertIn("不得直接输出 prose", contracts)

        gate = (root / "release_gate.md").read_text(encoding="utf-8")
        self.assertIn("Object Completeness", gate)
        self.assertIn("Specialist Quality", gate)
        self.assertIn("Utility / Review", gate)
        self.assertIn("新增 lexical fallback", gate)

        retirement = (root / "legacy_retirement_map.json").read_text(encoding="utf-8")
        self.assertIn("full_report_service", retirement)
        self.assertIn("cleanup_ready", retirement)
        self.assertIn("required_guard_tests", retirement)
        self.assertIn("delete_order", retirement)
        self.assertIn("blocking_smoke", retirement)
        self.assertIn("implementation_removed", retirement)

        runtime_surface = (root / "runtime_surface_alignment.md").read_text(encoding="utf-8")
        self.assertIn("thread_id", runtime_surface)
        self.assertIn("artifact_manifest", runtime_surface)
        self.assertIn("topic/date", runtime_surface)

        smoke = (root / "smoke_scenarios.md").read_text(encoding="utf-8")
        self.assertIn("Happy Path E2E", smoke)
        self.assertIn("Semantic Review Path", smoke)
        self.assertIn("Fallback Recompile Path", smoke)
        self.assertIn("Resume After Failure Path", smoke)
        self.assertIn("spawn EPERM", smoke)

    def test_legacy_retirement_map_encodes_delete_order_and_runtime_blockers(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "report" / "audit"
        payload = json.loads((root / "legacy_retirement_map.json").read_text(encoding="utf-8"))
        targets = payload["retirement_targets"]
        delete_order = [item["delete_order"] for item in targets]
        self.assertEqual(delete_order, sorted(delete_order))
        runtime = next(item for item in targets if item["module"] == "runtime")
        self.assertFalse(runtime["still_imported"])
        self.assertTrue(runtime["cleanup_ready"])
        self.assertTrue(runtime["implementation_removed"])
        self.assertIn("Resume After Failure Path", runtime["blocking_smoke"])
        self.assertIn(
            "backend.tests.test_report_contract_guards.ReportContractGuardTests.test_runtime_compat_bridge_is_removed_and_cannot_reenter_mainline",
            runtime["required_guard_tests"],
        )
        full_report = next(item for item in targets if item["module"] == "full_report_service")
        self.assertIn(
            "backend.tests.test_report_contract_guards.ReportContractGuardTests.test_removed_legacy_services_are_recorded_in_retirement_map",
            full_report["required_guard_tests"],
        )
        self.assertNotIn(
            "backend.tests.test_report_contract_guards.ReportContractGuardTests.test_legacy_full_report_service_is_quarantined",
            full_report["required_guard_tests"],
        )
        removed = {item["module"] for item in targets if item.get("implementation_removed")}
        self.assertEqual(removed, {"full_report_service", "structured_service", "runtime"})


if __name__ == "__main__":
    unittest.main()
