from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.presenter import render_markdown


ROOT = Path(__file__).resolve().parents[1] / "src" / "report"


class ReportContractGuardTests(unittest.TestCase):
    def test_api_and_worker_do_not_reimport_full_report_service_entrypoint(self) -> None:
        api_text = (ROOT / "api.py").read_text(encoding="utf-8")
        worker_text = (ROOT / "worker.py").read_text(encoding="utf-8")
        self.assertNotIn("from .full_report_service import", api_text)
        self.assertNotIn("from .structured_service import", api_text)
        self.assertNotIn("from src.report.full_report_service import", worker_text)
        self.assertNotIn("from src.report.structured_service import", worker_text)
        self.assertNotIn("full_report_service.generate_full_report_payload", api_text)
        self.assertNotIn("full_report_service.generate_full_report_payload", worker_text)
        self.assertNotIn("structured_service.generate_report_payload", api_text)
        self.assertNotIn("structured_service.generate_report_payload", worker_text)

    def test_runtime_compat_bridge_is_removed_and_cannot_reenter_mainline(self) -> None:
        api_text = (ROOT / "api.py").read_text(encoding="utf-8")
        worker_text = (ROOT / "worker.py").read_text(encoding="utf-8")
        deterministic_text = (ROOT / "deep_report" / "deterministic.py").read_text(encoding="utf-8")

        self.assertNotIn("from .runtime import", api_text)
        self.assertNotIn("from src.report.runtime import", worker_text)
        self.assertNotIn("from ..runtime import", deterministic_text)
        self.assertIn("runtime_bootstrap", worker_text)
        self.assertIn("runtime_bootstrap", deterministic_text)
        self.assertFalse((ROOT / "runtime.py").exists())

    def test_mainline_runtime_no_longer_uses_ready_booleans_or_legacy_progress_fallback(self) -> None:
        api_text = (ROOT / "api.py").read_text(encoding="utf-8")
        worker_text = (ROOT / "worker.py").read_text(encoding="utf-8")
        queue_text = (ROOT / "task_queue.py").read_text(encoding="utf-8")
        service_text = (ROOT / "deep_report" / "service.py").read_text(encoding="utf-8")

        self.assertNotIn("report_ready", api_text)
        self.assertNotIn("full_report_ready", api_text)
        self.assertNotIn("_collect_legacy_report_progress", api_text)
        self.assertNotIn("collect_explain_outputs", api_text)
        self.assertNotIn("report_ready", worker_text)
        self.assertNotIn("full_report_ready", worker_text)
        self.assertNotIn("report_ready", queue_text)
        self.assertNotIn("full_report_ready", queue_text)
        self.assertNotIn("report_ready", service_text)
        self.assertNotIn("full_report_ready", service_text)

    def test_prompt_templates_no_longer_accept_legacy_rag_keys(self) -> None:
        prompt_text = (ROOT / "structured_prompts.py").read_text(encoding="utf-8")
        self.assertNotIn("legacy_rag_sections", prompt_text)
        self.assertNotIn("legacy_report_text", prompt_text)

    def test_deep_report_compiler_main_impl_lives_in_compiler_module(self) -> None:
        presenter_text = (ROOT / "deep_report" / "presenter.py").read_text(encoding="utf-8")
        compiler_text = (ROOT / "deep_report" / "compiler.py").read_text(encoding="utf-8")
        service_text = (ROOT / "deep_report" / "service.py").read_text(encoding="utf-8")
        self.assertIn("resolve_style_profile", compiler_text)
        self.assertIn("build_layout_plan", compiler_text)
        self.assertIn("build_section_budget", compiler_text)
        self.assertIn("build_section_plan", compiler_text)
        self.assertIn("build_conformance_policy_registry", compiler_text)
        self.assertIn("ConformanceExecutor", compiler_text)
        self.assertIn("compile_draft_units", compiler_text)
        self.assertIn("run_factual_conformance", compiler_text)
        self.assertIn("run_stylistic_rewrite", compiler_text)
        self.assertIn("sanitize_public_markdown", compiler_text)
        self.assertIn("render_final_markdown", compiler_text)
        self.assertNotIn("full_report_service", presenter_text)
        self.assertIn("graph_interrupt", service_text)

    def test_render_markdown_refuses_raw_structured_payload_without_report_ir(self) -> None:
        with self.assertRaises(ValueError):
            render_markdown({"task": {"topic_label": "示例专题"}})

    def test_removed_legacy_services_are_recorded_in_retirement_map(self) -> None:
        self.assertFalse((ROOT / "full_report_service.py").exists())
        self.assertFalse((ROOT / "structured_service.py").exists())
        retirement = (ROOT / "audit" / "legacy_retirement_map.json").read_text(encoding="utf-8")
        self.assertIn('"module": "full_report_service"', retirement)
        self.assertIn('"module": "structured_service"', retirement)
        self.assertIn('"implementation_removed": true', retirement)

    def test_runtime_bridge_is_recorded_as_removed_in_retirement_map(self) -> None:
        self.assertFalse((ROOT / "runtime.py").exists())
        retirement = (ROOT / "audit" / "legacy_retirement_map.json").read_text(encoding="utf-8")
        self.assertIn('"module": "runtime"', retirement)
        self.assertIn('"implementation_removed": true', retirement)

    def test_compiler_passes_remain_agent_free(self) -> None:
        compiler_text = (ROOT / "deep_report" / "compiler.py").read_text(encoding="utf-8")
        self.assertNotIn("call_langchain_chat", compiler_text)
        self.assertNotIn("call_langchain_with_tools", compiler_text)
        self.assertNotIn("create_deep_agent", compiler_text)
        self.assertIn("policy.v2", compiler_text)
        self.assertNotIn("舆论普遍反对", compiler_text)
        self.assertNotIn("风险已形成", compiler_text)
        self.assertNotIn("必须立即处理", compiler_text)
        self.assertNotIn("社会普遍认为", compiler_text)

    def test_deep_report_service_does_not_call_legacy_writer_or_critics(self) -> None:
        service_text = (ROOT / "deep_report" / "service.py").read_text(encoding="utf-8")
        self.assertNotIn("generate_section_markdown(", service_text)
        self.assertNotIn("_call_style_critic(", service_text)
        self.assertNotIn("_call_fact_critic(", service_text)

    def test_deep_report_service_no_longer_imports_duplicate_tool_registry(self) -> None:
        service_text = (ROOT / "deep_report" / "service.py").read_text(encoding="utf-8")
        self.assertNotIn("tool_registry", service_text)
        self.assertFalse((ROOT / "deep_report" / "tool_registry.py").exists())

    def test_production_runtime_modules_use_runtime_infra_not_memory_savers(self) -> None:
        runtime_modules = [
            ROOT / "agent_runtime.py",
            ROOT / "deep_report" / "service.py",
            ROOT / "deep_report" / "orchestrator_graph.py",
            ROOT / "deep_report" / "graph_runtime.py",
        ]
        for path in runtime_modules:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("InMemorySaver", text)
            self.assertIn("runtime_infra", text)

    def test_capability_audit_artifacts_exist_for_tool_and_skill_planning(self) -> None:
        audit_root = ROOT / "audit"
        self.assertTrue((audit_root / "capability_map.md").exists())
        self.assertTrue((audit_root / "tool_authoring_standard.md").exists())
        self.assertTrue((audit_root / "tool_migration_backlog.json").exists())

    def test_semantic_runtime_examples_stay_out_of_production_modules(self) -> None:
        semantic_text = (ROOT / "deep_report" / "semantic_control.py").read_text(encoding="utf-8")
        self.assertNotIn("舆论普遍反对", semantic_text)
        self.assertNotIn("风险已形成", semantic_text)
        self.assertNotIn("必须立即处理", semantic_text)
        self.assertNotIn("社会普遍认为", semantic_text)


if __name__ == "__main__":
    unittest.main()
