from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.runtime_infra import build_report_runnable_config, build_runtime_diagnostics, resolve_runtime_profile


POSTGRES_DATABASES = {
    "active": "primary",
    "connections": [
        {
            "id": "primary",
            "name": "本地 PostgreSQL",
            "engine": "postgresql",
            "url": "postgresql+psycopg2://postgres:secret@localhost:5432/postgres",
        }
    ],
}

MYSQL_DATABASES = {
    "active": "primary",
    "connections": [
        {
            "id": "primary",
            "name": "本地 MySQL",
            "engine": "mysql",
            "url": "mysql+pymysql://root:secret@localhost:3306/app",
        }
    ],
}


class ReportRuntimeInfraTests(unittest.TestCase):
    def test_development_profile_defaults_to_sqlite(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPINION_REPORT_RUNTIME_ENV": "development",
                "OPINION_REPORT_CHECKPOINTER_BACKEND": "sqlite",
            },
            clear=False,
        ):
            profile = resolve_runtime_profile(
                purpose="unit-test",
                locator_hint="f:/opinion-system/backend/data/_report/checkpoints/unit-test.sqlite",
            )

        self.assertEqual(profile.environment, "development")
        self.assertEqual(profile.checkpointer_backend, "sqlite")
        self.assertTrue(profile.checkpoint_path.endswith("unit-test.sqlite"))

    def test_production_profile_rejects_sqlite_backend(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPINION_REPORT_RUNTIME_ENV": "production",
                "OPINION_REPORT_CHECKPOINTER_BACKEND": "sqlite",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                resolve_runtime_profile(purpose="unit-test")

        self.assertIn("requires PostgresSaver", str(ctx.exception))

    def test_postgres_profile_reuses_active_database_connection(self) -> None:
        with patch("src.report.runtime_infra.load_databases_config", return_value=POSTGRES_DATABASES), patch(
            "src.report.runtime_infra.load_llm_config",
            return_value={
                "langchain": {
                    "report": {
                        "runtime": {
                            "environment": "production",
                            "persistence": {"enabled": True, "backend": "postgres", "source_mode": "reuse_active", "schema_name": "report_runtime"},
                            "observability": {"langsmith": {"enabled": True, "project": "opinion-system-report", "endpoint": "https://api.smith.langchain.com"}},
                        }
                    }
                },
                "credentials": {"langsmith_api_key": "lsv2_pt_test"},
            },
        ), patch.dict(os.environ, {}, clear=False):
            profile = resolve_runtime_profile(purpose="deep-report-coordinator")
            config = build_report_runnable_config(thread_id="thread-1", purpose="deep-report-coordinator", task_id="task-1")
            diagnostics = build_runtime_diagnostics(thread_id="thread-1", purpose="deep-report-coordinator", task_id="task-1")

            self.assertEqual(os.environ.get("LANGSMITH_ENDPOINT"), "https://api.smith.langchain.com")
            self.assertEqual(os.environ.get("LANGSMITH_API_KEY"), "lsv2_pt_test")

        self.assertEqual(profile.checkpointer_backend, "postgres")
        self.assertEqual(profile.connection_id, "primary")
        self.assertEqual(profile.schema_name, "report_runtime")
        self.assertEqual(profile.resolved_database, "postgres")
        self.assertEqual(diagnostics["connection_id"], "primary")
        self.assertEqual(diagnostics["schema_name"], "report_runtime")
        self.assertEqual(config["metadata"]["report_runtime"]["resolved_database"], "postgres")

    def test_postgres_profile_rejects_non_postgres_active_connection(self) -> None:
        with patch("src.report.runtime_infra.load_databases_config", return_value=MYSQL_DATABASES), patch(
            "src.report.runtime_infra.load_llm_config",
            return_value={
                "langchain": {
                    "report": {
                        "runtime": {
                            "environment": "production",
                            "persistence": {"enabled": True, "backend": "postgres", "source_mode": "reuse_active", "schema_name": "report_runtime"},
                        }
                    }
                }
            },
        ), patch.dict(os.environ, {}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                resolve_runtime_profile(purpose="unit-test")

        self.assertIn("requires the active database connection to be PostgreSQL", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
