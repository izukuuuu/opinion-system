from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.netinsight import planner  # noqa: E402


class NetInsightPlannerTests(unittest.TestCase):
    def _plan(self, brief: str) -> dict:
        with patch.object(planner, "_llm_plan", return_value=None):
            return planner.plan_task_from_brief(brief)

    def test_domestic_scope_defaults_to_domestic_platforms(self) -> None:
        plan = self._plan("国内控烟舆情，最近一周，关注微博和新闻")

        self.assertEqual(plan["scope"], "domestic")
        self.assertIn("微博", plan["platforms"])
        self.assertIn("新闻网站", plan["platforms"])
        self.assertNotIn("Facebook", plan["platforms"])
        self.assertTrue(plan["keywords"])

    def test_foreign_scope_defaults_to_foreign_platforms(self) -> None:
        plan = self._plan("国外媒体关于电子烟监管的讨论")

        self.assertEqual(plan["scope"], "foreign")
        self.assertEqual(plan["platforms"], ["境外新闻", "Facebook", "Twitter"])
        self.assertTrue(plan["keywords"])

    def test_global_scope_expands_to_explicit_platforms(self) -> None:
        plan = self._plan("全球范围关注新能源汽车安全舆情")

        self.assertEqual(plan["scope"], "global")
        self.assertNotIn("全部", plan["platforms"])
        self.assertIn("微博", plan["platforms"])
        self.assertIn("Facebook", plan["platforms"])
        self.assertIn("Twitter", plan["platforms"])

    def test_llm_all_platforms_are_expanded_by_scope(self) -> None:
        with patch.object(
            planner,
            "_llm_plan",
            return_value={"scope": "global", "platforms": ["全部"], "keywords": ["测试"]},
        ):
            plan = planner.plan_task_from_brief("全球范围测试")

        self.assertEqual(plan["scope"], "global")
        self.assertNotIn("全部", plan["platforms"])
        self.assertEqual(plan["platforms"], planner.GLOBAL_PLATFORMS)


if __name__ == "__main__":
    unittest.main()
