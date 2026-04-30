from __future__ import annotations

import io
import json
import shutil
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server_support.topic_context import TopicContext
from src.report import cli as report_cli


class ReportCliTests(unittest.TestCase):
    def _make_tmp_dir(self, name: str) -> Path:
        root = Path(__file__).resolve().parents[1] / "data" / "_tmp_report_cli_tests" / name
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_run_uses_api_aligned_default_range_when_start_end_omitted(self) -> None:
        tmp_dir = self._make_tmp_dir("run-default-range")
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        captured = {}
        event_path = tmp_dir / "events.jsonl"

        def _fake_run(topic_identifier, start, end, **kwargs):
            captured["topic_identifier"] = topic_identifier
            captured["start"] = start
            captured["end"] = end
            callback = kwargs.get("event_callback")
            if callable(callback):
                callback({"type": "phase.progress", "phase": "prepare", "message": "started"})
            return {
                "status": "completed",
                "message": "ok",
                "thread_id": "thread-1",
                "structured_payload": {
                    "metadata": {
                        "workspace_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31",
                        "state_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31/state",
                        "todos": [],
                    }
                },
                "full_payload": {},
                "exploration_bundle": {"gap_summary": [], "todos": []},
            }

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch(
            "src.report.cli._resolve_report_range",
            return_value=(
                ctx,
                [{"start": "2025-01-01", "end": "2025-01-31"}],
                [],
                {"start": "2024-12-01", "end": "2025-01-31"},
            ),
        ), patch(
            "src.report.cli.ensure_cache_dir_v2",
            return_value=tmp_dir,
        ), patch(
            "src.report.cli.run_or_resume_deep_report_task",
            side_effect=_fake_run,
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = report_cli.main(
                    ["run", "--topic", "示例专题", "--event-log", str(event_path), "--json"]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["topic_identifier"], "demo-topic")
        self.assertEqual(captured["start"], "2025-01-01")
        self.assertEqual(captured["end"], "2025-01-31")
        self.assertTrue(event_path.exists())
        self.assertTrue((tmp_dir / report_cli.DEFAULT_DEBUG_SUMMARY_FILENAME).exists())

    def test_run_writes_event_log_and_debug_summary(self) -> None:
        tmp_dir = self._make_tmp_dir("run-artifacts")
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        event_path = tmp_dir / "custom-events.jsonl"

        def _fake_run(_topic_identifier, _start, _end, **kwargs):
            callback = kwargs.get("event_callback")
            if callable(callback):
                callback({"type": "graph.node.started", "phase": "exploration", "agent": "retrieval_router", "message": "running"})
            return {
                "status": "completed",
                "message": "ok",
                "thread_id": "thread-1",
                "structured_payload": {
                    "metadata": {
                        "workspace_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31",
                        "state_root": "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31/state",
                        "todos": [{"id": "tier-1", "status": "completed"}],
                        "execution_plan": {"nodes": {}},
                        "reused_artifacts": {"evidence_cards": {"source_report_range": "2024-12-01_2024-12-31"}},
                        "skipped_agents": {"archive_evidence_organizer": {"reason": "reused_from_history"}},
                    }
                },
                "full_payload": {},
                "exploration_bundle": {
                    "gap_summary": [],
                    "todos": [{"id": "tier-1", "status": "completed"}],
                    "artifact_semantic_status": {"evidence_cards.json": {"status": "ready"}},
                    "readiness_gate_passed": True,
                    "repair_attempts": 1,
                    "repair_trace": [{"target_agent": "archive_evidence_organizer", "status": "ready"}],
                    "blocked_stage": "",
                },
            }

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch(
            "src.report.cli._resolve_report_range",
            return_value=(ctx, [], [], {"start": "2025-01-01", "end": "2025-01-31"}),
        ), patch(
            "src.report.cli.ensure_cache_dir_v2",
            return_value=tmp_dir,
        ), patch(
            "src.report.cli.run_or_resume_deep_report_task",
            side_effect=_fake_run,
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = report_cli.main(
                    ["run", "--topic", "示例专题", "--event-log", str(event_path)]
                )

        self.assertEqual(exit_code, 0)
        event_lines = event_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(event_lines), 1)
        summary = json.loads((tmp_dir / report_cli.DEFAULT_DEBUG_SUMMARY_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["workspace_root"], "/workspace/projects/demo-project/reports/2025-01-01_2025-01-31")
        self.assertIn("execution_plan", summary)
        self.assertIn("reused_artifacts", summary)
        self.assertIn("skipped_agents", summary)
        self.assertTrue(summary["readiness_gate_passed"])
        self.assertEqual(summary["repair_attempts"], 1)
        self.assertIn("artifact_semantic_status", summary)

    def test_harness_flags_retrieval_success_without_persisted_evidence_cards(self) -> None:
        tmp_dir = self._make_tmp_dir("retrieval-lineage")
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        event_path = tmp_dir / "events.jsonl"

        def _fake_run(_topic_identifier, _start, _end, **kwargs):
            callback = kwargs.get("event_callback")
            if callable(callback):
                callback(
                    {
                        "type": "agent.memo",
                        "phase": "interpret",
                        "agent": "archive_evidence_organizer",
                        "message": "已召回 12 张证据卡，覆盖 5 个平台。",
                        "payload": {
                            "tool_name": "retrieve_evidence_cards",
                            "counts": {"matched_count": 27, "sampled_count": 12, "platform_count": 5, "cards_count": 12},
                        },
                    }
                )
            return {
                "status": "failed",
                "message": "探索阶段未通过 readiness gate，已阻断 compile。",
                "thread_id": "thread-1",
                "structured_payload": {},
                "full_payload": {},
                "exploration_bundle": {
                    "gap_summary": [{"agent": "archive_evidence_organizer", "file": "evidence_cards.json", "reason": "empty"}],
                    "artifact_semantic_status": {"evidence_cards.json": {"status": "empty"}},
                    "readiness_gate_passed": False,
                    "blocked_stage": "exploration_readiness",
                },
            }

        with patch(
            "src.report.cli._resolve_report_range",
            return_value=(ctx, [], [], {"start": "2025-01-01", "end": "2025-01-31"}),
        ), patch(
            "src.report.cli.ensure_cache_dir_v2",
            return_value=tmp_dir,
        ), patch(
            "src.report.cli.run_or_resume_deep_report_task",
            side_effect=_fake_run,
        ):
            exit_code = report_cli.main(
                ["run", "--topic", "示例专题", "--event-log", str(event_path), "--quiet-events", "--json"]
            )

        self.assertEqual(exit_code, 1)
        summary = json.loads((tmp_dir / report_cli.DEFAULT_DEBUG_SUMMARY_FILENAME).read_text(encoding="utf-8"))
        checks = {item["name"]: item for item in summary["harness_scorecard"]["checks"]}
        self.assertEqual(checks["retrieval_lineage"]["status"], "fail")
        self.assertEqual(checks["retrieval_lineage"]["reason"], "retrieval_result_not_persisted")
        self.assertEqual(checks["retrieval_lineage"]["retrieval_counts"]["cards_count"], 12)

    def test_availability_outputs_current_default_range_only(self) -> None:
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        stdout = io.StringIO()
        with patch(
            "src.report.cli._resolve_report_range",
            return_value=(
                ctx,
                [{"start": "2025-02-01", "end": "2025-02-28"}],
                [{"start": "2025-01-01", "end": "2025-01-31"}],
                {"start": "2024-01-01", "end": "2025-02-28"},
            ),
        ):
            with redirect_stdout(stdout):
                exit_code = report_cli.main(["availability", "--topic", "示例专题"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["range"]["start"], "2025-02-01")
        self.assertEqual(payload["topic_identifier"], "demo-topic")

    def test_render_html_fixture_writes_replayable_html_and_scorecard(self) -> None:
        tmp_dir = self._make_tmp_dir("render-html-fixture")
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "report_html_2025_tobacco.json"
        output_path = tmp_dir / "ai_full_report.html"
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = report_cli.main(
                [
                    "render-html-fixture",
                    "--fixture",
                    str(fixture_path),
                    "--output",
                    str(output_path),
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_path.exists())
        html = output_path.read_text(encoding="utf-8")
        self.assertIn("echarts.init", html)
        self.assertIn("keywordCloud", html)
        self.assertNotIn("证据不足", html)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["scorecard"]["status"], "passed")
        self.assertGreaterEqual(summary["report_data_summary"]["keyword_count"], 6)

    def test_render_html_cache_can_overlay_exploration_artifacts(self) -> None:
        tmp_dir = self._make_tmp_dir("render-html-cache-overlay")
        cache_dir = tmp_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / report_cli.AI_FULL_REPORT_CACHE_FILENAME).write_text(
            json.dumps(
                {
                    "task": {"topic_label": "2025控烟舆情"},
                    "markdown": "# 2025控烟舆情\n\n基础文稿。",
                    "timeline": [],
                    "citations": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (cache_dir / report_cli.REPORT_CACHE_FILENAME).write_text("{}", encoding="utf-8")
        overlay_path = Path(__file__).resolve().parent / "fixtures" / "report_html_exploration_overlay_highspeed_smoking.json"
        output_path = tmp_dir / "probe.html"
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = report_cli.main(
                [
                    "render-html-cache",
                    "--cache-dir",
                    str(cache_dir),
                    "--exploration-overlay",
                    str(overlay_path),
                    "--output",
                    str(output_path),
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        html = output_path.read_text(encoding="utf-8")
        self.assertIn("高铁站台控烟", html)
        self.assertIn("12306回应", html)
        self.assertIn("旅客与通勤人群", html)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["scorecard"]["status"], "passed")
        self.assertEqual(summary["report_data_summary"]["timeline_count"], 2)

    def test_probe_html_llm_graph_checkpoints_eval_gates_and_resumes(self) -> None:
        tmp_dir = self._make_tmp_dir("probe-html-llm-graph")
        cache_dir = tmp_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / report_cli.AI_FULL_REPORT_CACHE_FILENAME).write_text(
            json.dumps(
                {
                    "task": {"topic_label": "2025控烟舆情"},
                    "markdown": "# 2025控烟舆情\n\n高铁站台控烟议题升温。",
                    "timeline": [],
                    "citations": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (cache_dir / report_cli.REPORT_CACHE_FILENAME).write_text("{}", encoding="utf-8")
        output_path = tmp_dir / "llm-probe.html"
        thread_id = "probe-html-llm-test-thread"
        stdout = io.StringIO()

        class FakeLlm:
            def invoke(self, _messages):
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": json.dumps(
                            {
                                "payload": {
                                    "evidence_cards": {
                                        "status": "ready",
                                        "result": [
                                            {
                                                "title": "高铁站台控烟回应引发讨论",
                                                "snippet": "公众追问站台禁烟边界。",
                                                "published_at": "2025-08-21",
                                                "sentiment": "负面",
                                                "keywords": ["高铁站台控烟", "站台禁烟"],
                                            }
                                        ],
                                    },
                                    "timeline_nodes": {
                                        "status": "ready",
                                        "result": [{"time": "2025-08-21", "event": "高铁站台控烟回应引发讨论。"}],
                                    },
                                    "metrics_bundle": {"status": "ready", "result": [{"date": "2025-08-21", "value": 300}]},
                                    "actor_positions": {"status": "ready", "result": [{"actor_name": "旅客群体", "mentions": 9}]},
                                    "event_analysis": {
                                        "status": "ready",
                                        "result": {
                                            "summary": "规则适用边界成为核心争点。",
                                            "sentiment_summary": {"negative": 7, "neutral": 3, "positive": 1},
                                            "keywords": ["高铁站台控烟", "站台禁烟"],
                                        },
                                    },
                                }
                            },
                            ensure_ascii=False,
                        )
                    },
                )()

        with patch("src.report.cli.build_langchain_chat_model", return_value=(FakeLlm(), {"provider": "fake", "model": "fake-chat", "model_role": "report"})):
            with redirect_stdout(stdout):
                exit_code = report_cli.main(
                    [
                        "probe-html-llm-graph",
                        "--cache-dir",
                        str(cache_dir),
                        "--output",
                        str(output_path),
                        "--thread-id",
                        thread_id,
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["status"], "interrupted")
        self.assertEqual(summary["thread_id"], thread_id)
        self.assertIn("eval_gate_after_llm", summary["next"])
        self.assertFalse(output_path.exists())
        self.assertTrue((cache_dir / "llm_exploration.scorecard.json").exists())

        inspect_stdout = io.StringIO()
        with redirect_stdout(inspect_stdout):
            inspect_exit = report_cli.main(
                [
                    "inspect-state",
                    "--runtime",
                    "probe",
                    "--thread-id",
                    thread_id,
                    "--cache-dir",
                    str(cache_dir),
                    "--output",
                    str(output_path),
                    "--json",
                ]
            )
        self.assertEqual(inspect_exit, 0)
        inspect_summary = json.loads(inspect_stdout.getvalue())
        self.assertEqual(inspect_summary["snapshot"]["values"]["stage"], "llm_exploration")
        self.assertTrue(inspect_summary["snapshot"]["interrupts"])

        history_stdout = io.StringIO()
        with redirect_stdout(history_stdout):
            history_exit = report_cli.main(
                [
                    "history",
                    "--runtime",
                    "probe",
                    "--thread-id",
                    thread_id,
                    "--cache-dir",
                    str(cache_dir),
                    "--output",
                    str(output_path),
                    "--json",
                ]
            )
        self.assertEqual(history_exit, 0)
        history_summary = json.loads(history_stdout.getvalue())
        self.assertGreaterEqual(history_summary["count"], 2)

        eval_stdout = io.StringIO()
        with redirect_stdout(eval_stdout):
            eval_exit = report_cli.main(
                [
                    "eval-stage",
                    "--runtime",
                    "probe",
                    "--thread-id",
                    thread_id,
                    "--cache-dir",
                    str(cache_dir),
                    "--stage",
                    "llm_exploration",
                    "--json",
                ]
            )
        self.assertEqual(eval_exit, 0)
        self.assertEqual(json.loads(eval_stdout.getvalue())["status"], "passed")

        resume_stdout = io.StringIO()
        with redirect_stdout(resume_stdout):
            resume_exit = report_cli.main(
                [
                    "continue",
                    "--runtime",
                    "probe",
                    "--thread-id",
                    thread_id,
                    "--cache-dir",
                    str(cache_dir),
                    "--output",
                    str(output_path),
                    "--json",
                ]
            )

        self.assertEqual(resume_exit, 0)
        resume_summary = json.loads(resume_stdout.getvalue())
        self.assertEqual(resume_summary["status"], "interrupted")
        self.assertIn("eval_gate_after_render", resume_summary["next"])
        html = output_path.read_text(encoding="utf-8")
        self.assertIn("高铁站台控烟", html)
        self.assertIn("旅客群体", html)
        self.assertTrue((cache_dir / "render_html.scorecard.json").exists())

        final_stdout = io.StringIO()
        with redirect_stdout(final_stdout):
            final_exit = report_cli.main(
                [
                    "resume",
                    "--runtime",
                    "probe",
                    "--thread-id",
                    thread_id,
                    "--decision",
                    "continue",
                    "--cache-dir",
                    str(cache_dir),
                    "--output",
                    str(output_path),
                    "--json",
                ]
            )
        self.assertEqual(final_exit, 0)
        final_summary = json.loads(final_stdout.getvalue())
        self.assertEqual(final_summary["status"], "completed")

    def test_replay_task_can_build_failure_resume_context(self) -> None:
        tmp_dir = self._make_tmp_dir("replay-task")
        event_path = tmp_dir / "events.jsonl"
        task = {
            "id": "rp-task-1",
            "topic": "示例专题",
            "topic_identifier": "demo-topic",
            "thread_id": "report::demo-topic::2025-01-01::2025-01-31",
            "start": "2025-01-01",
            "end": "2025-01-31",
            "mode": "fast",
            "request": {"project": "Demo Project", "dataset_id": "", "skip_validation": False},
        }
        ctx = TopicContext(identifier="demo-topic", project_identifier="demo-project", display_name="示例专题")
        captured = {}

        def _fake_run(_topic_identifier, _start, _end, **kwargs):
            captured["failure_resume_context"] = kwargs.get("failure_resume_context")
            callback = kwargs.get("event_callback")
            if callable(callback):
                callback({"type": "phase.progress", "phase": "compile", "message": "resume"})
            return {
                "status": "completed",
                "message": "ok",
                "thread_id": "thread-1",
                "structured_payload": {"metadata": {}},
                "full_payload": {},
                "exploration_bundle": {"gap_summary": [], "todos": []},
            }

        with patch("src.report.cli.get_task", return_value=task), patch(
            "src.report.cli.evaluate_resume_before_failure",
            return_value={
                "enabled": True,
                "source_phase": "compile",
                "source_actor": "markdown_compiler",
                "structured_cache_path": str(tmp_dir / "report_payload.json"),
            },
        ), patch(
            "src.report.cli._resolve_report_range",
            return_value=(ctx, [], [], {"start": "2025-01-01", "end": "2025-01-31"}),
        ), patch(
            "src.report.cli.ensure_cache_dir_v2",
            return_value=tmp_dir,
        ), patch(
            "src.report.cli.run_or_resume_deep_report_task",
            side_effect=_fake_run,
        ):
            exit_code = report_cli.main(
                ["replay-task", "--task-id", "rp-task-1", "--resume-before-failure", "--event-log", str(event_path), "--quiet-events"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["failure_resume_context"]["source_task_id"], "rp-task-1")
        self.assertEqual(captured["failure_resume_context"]["source_failed_phase"], "compile")


if __name__ == "__main__":
    unittest.main()
