from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.html_report_renderer import build_html_report_artifact


class HtmlReportRendererTests(unittest.TestCase):
    def test_renderer_builds_echarts_data_from_exploration_artifacts(self) -> None:
        state = {
            "task": {
                "topic_label": "2025控烟舆情",
                "topic_identifier": "2025-smoking-control",
            },
            "markdown": "# 2025控烟舆情\n\n公共场所控烟、电子烟、未成年人保护是核心议题。",
            "payload": {
                "evidence_cards": {
                    "status": "ready",
                    "result": [
                        {
                            "evidence_id": "ev-1",
                            "title": "餐厅控烟讨论升温",
                            "snippet": "二手烟和餐厅吸烟引发投诉。",
                            "platform": "微博",
                            "province": "北京",
                            "author": "健康时报",
                            "published_at": "2025-05-20",
                            "sentiment": "负面",
                            "keywords": ["二手烟", "餐厅吸烟", "控烟执法"],
                        },
                        {
                            "evidence_id": "ev-2",
                            "title": "无烟日科普传播",
                            "snippet": "未成年人保护和电子烟监管获得支持。",
                            "platform": "新闻",
                            "province": "上海",
                            "author": "地方政务",
                            "published_at": "2025-05-31",
                            "sentiment": "正面",
                            "keywords": ["未成年人", "电子烟", "无烟日"],
                        },
                    ],
                },
                "timeline_nodes": {
                    "status": "ready",
                    "result": [
                        {"time": "2025 Q1", "event": "校园周边电子烟营销引发讨论。"},
                        {"time": "2025-05", "event": "世界无烟日前后控烟声量抬升。"},
                    ],
                },
                "metrics_bundle": {
                    "status": "ready",
                    "result": [
                        {"date": "2025-05", "value": 128},
                        {"date": "2025-06", "value": 86},
                    ],
                },
                "actor_positions": {
                    "status": "ready",
                    "result": [
                        {"actor_name": "家长群体", "mentions": 12},
                        {"actor_name": "公共场所管理方", "mentions": 8},
                    ],
                },
            },
        }

        with patch("src.report.deep_report.html_report_renderer.build_langchain_chat_model", return_value=(None, {})):
            artifact = build_html_report_artifact(state)

        html = artifact["html"]
        self.assertIn("echarts.init", html)
        self.assertIn("setOption", html)
        self.assertIn("keywordCloud", html)
        self.assertIn("timelineList", html)
        self.assertIn("二手烟", html)
        self.assertIn("健康时报", html)
        self.assertNotIn("__REPORT_JSON_DATA__", html)
        self.assertNotIn("{{REPORT_TITLE}}", html)
        self.assertGreaterEqual(artifact["report_data_summary"]["keyword_count"], 6)
        self.assertEqual(artifact["report_data_summary"]["timeline_count"], 2)


if __name__ == "__main__":
    unittest.main()
