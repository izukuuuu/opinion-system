from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server_support.settings_config import register_settings_endpoints


class ReportRuntimeSettingsApiTests(unittest.TestCase):
    def _client(self):
        app = Flask(__name__)
        register_settings_endpoints(app, project_manager=None)
        return app.test_client()

    def test_get_report_runtime_returns_model_and_persistence_summary(self) -> None:
        llm_config = {
            "langchain": {
                "report": {
                    "runtime": {
                        "model": {"provider": "openai", "model": "glm-5", "base_url": "https://example.com", "temperature": 0.2, "max_tokens": 18000, "timeout": 420.0, "max_retries": 2},
                        "persistence": {"enabled": True, "source_mode": "reuse_active", "schema_name": "report_runtime"},
                    }
                }
            },
            "credentials": {"report_api_key": "sk-test-1234"},
        }
        databases = {
            "active": "primary",
            "connections": [{"id": "primary", "name": "本地 PostgreSQL", "engine": "postgresql", "url": "postgresql+psycopg2://postgres:secret@localhost:5432/postgres"}],
        }
        client = self._client()
        with patch("server_support.settings_config.load_llm_config", return_value=llm_config), patch(
            "server_support.settings_config.load_databases_config", return_value=databases
        ):
            response = client.get("/api/settings/llm/report-runtime")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["provider"], "openai")
        self.assertEqual(data["persistence"]["active_connection_id"], "primary")
        self.assertEqual(data["persistence"]["schema_name"], "report_runtime")

    def test_put_report_runtime_persistence_writes_canonical_tree(self) -> None:
        stored = {"langchain": {"report": {"runtime": {"persistence": {"enabled": False, "source_mode": "reuse_active", "schema_name": "report_runtime"}}}}}
        databases = {
            "active": "primary",
            "connections": [{"id": "primary", "name": "本地 PostgreSQL", "engine": "postgresql", "url": "postgresql+psycopg2://postgres:secret@localhost:5432/postgres"}],
        }
        persisted = {}

        def _persist(config):
            persisted.update(config)

        client = self._client()
        with patch("server_support.settings_config.load_llm_config", return_value=stored), patch(
            "server_support.settings_config.load_databases_config", return_value=databases
        ), patch("server_support.settings_config.persist_llm_config", side_effect=_persist):
            response = client.put(
                "/api/settings/report-runtime/persistence",
                json={"enabled": True, "source_mode": "reuse_active", "schema_name": "runtime_checkpoint"},
            )

        self.assertEqual(response.status_code, 200)
        runtime = persisted["langchain"]["report"]["runtime"]
        self.assertEqual(runtime["persistence"]["enabled"], True)
        self.assertEqual(runtime["persistence"]["schema_name"], "runtime_checkpoint")

    def test_put_report_runtime_persistence_rejects_mysql_active_connection(self) -> None:
        stored = {"langchain": {"report": {"runtime": {"persistence": {"enabled": False, "source_mode": "reuse_active", "schema_name": "report_runtime"}}}}}
        databases = {
            "active": "primary",
            "connections": [{"id": "primary", "name": "本地 MySQL", "engine": "mysql", "url": "mysql+pymysql://root:secret@localhost:3306/app"}],
        }
        client = self._client()
        with patch("server_support.settings_config.load_llm_config", return_value=stored), patch(
            "server_support.settings_config.load_databases_config", return_value=databases
        ):
            response = client.put(
                "/api/settings/report-runtime/persistence",
                json={"enabled": True, "source_mode": "reuse_active", "schema_name": "runtime_checkpoint"},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload["status"], "error")


if __name__ == "__main__":
    unittest.main()
