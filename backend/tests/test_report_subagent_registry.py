from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.configs import _validate_subagents_config
from src.report.deep_report.compat import extract_legacy_interrupts, parse_structured_report_tool_input
from src.report.deep_report.subagent_registry import (
    build_tier_prompt_lines,
    get_exploration_artifact_owners,
    get_repair_agent_tiers,
    get_required_exploration_artifacts,
)


class ReportSubagentRegistryTests(unittest.TestCase):
    def test_validate_subagents_config_requires_tier_and_output_contract(self) -> None:
        with self.assertRaises(ValueError):
            _validate_subagents_config({"subagents": {"demo": {"skill_keys": []}}})

        with self.assertRaises(ValueError):
            _validate_subagents_config({"subagents": {"demo": {"tier": 1, "skill_keys": [], "output_files": "bad"}}})

    def test_registry_derives_required_artifacts_and_repair_tiers(self) -> None:
        fast = get_required_exploration_artifacts("fast")
        research = get_required_exploration_artifacts("research")
        owners = get_exploration_artifact_owners()
        tiers = get_repair_agent_tiers()

        self.assertIn("evidence_cards.json", fast)
        self.assertNotIn("bertopic_insight.json", fast)
        self.assertIn("bertopic_insight.json", research)
        self.assertEqual(owners["risk_signals.json"], "propagation_analyst")
        self.assertEqual(tiers["decision_utility_judge"], 5)
        self.assertNotIn("writer", tiers)

    def test_build_tier_prompt_lines_renders_yaml_order(self) -> None:
        with patch("src.report.deep_report.subagent_registry.get_tier_groups", return_value={0: ["retrieval_router"], 1: ["alpha", "beta"]}):
            lines = build_tier_prompt_lines()

        self.assertEqual(lines[0], "   Tier 0: retrieval_router")
        self.assertEqual(lines[1], "   Tier 1: alpha、beta（并行）")

    def test_compat_helpers_support_legacy_interrupt_and_payload_json(self) -> None:
        interrupts = extract_legacy_interrupts({"__interrupt__": [{"id": "legacy"}]})
        payload, meta = parse_structured_report_tool_input(None, '{"task":{"topic_label":"示例"}}')

        self.assertEqual(len(interrupts), 1)
        self.assertTrue(meta["compat_mode"])
        self.assertEqual(meta["source"], "payload_json")
        self.assertEqual(payload["task"]["topic_label"], "示例")


if __name__ == "__main__":
    unittest.main()
