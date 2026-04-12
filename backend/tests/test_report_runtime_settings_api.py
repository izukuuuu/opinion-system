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
                        "observability": {"langsmith": {"enabled": True, "project": "opinion-system-report", "endpoint": "https://api.smith.langchain.com"}},
                    }
                }
            },
            "credentials": {"report_api_key": "sk-test-1234", "langsmith_api_key": "lsv2_pt_test"},
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
        self.assertEqual(data["observability"]["project"], "opinion-system-report")
        self.assertEqual(data["observability"]["endpoint"], "https://api.smith.langchain.com")
        self.assertTrue(data["observability"]["api_key"]["configured"])

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

    def test_put_report_runtime_observability_writes_langsmith_config(self) -> None:
        stored = {"langchain": {"report": {"runtime": {"observability": {"langsmith": {"enabled": False, "project": "default"}}}}}}
        persisted = {}
        local_updates = []

        def _persist(config):
            persisted.update(config)

        client = self._client()
        with patch("server_support.settings_config.load_llm_config", return_value=stored), patch(
            "server_support.settings_config.persist_llm_config", side_effect=_persist
        ), patch(
            "server_support.settings_config.update_llm_local_secrets",
            side_effect=lambda **kwargs: local_updates.append(kwargs),
        ):
            response = client.put(
                "/api/settings/report-runtime/observability",
                json={
                    "enabled": True,
                    "project": "report-prod",
                    "endpoint": "https://api.smith.langchain.com",
                    "api_key": "lsv2_pt_test",
                },
            )

        self.assertEqual(response.status_code, 200)
        langsmith = persisted["langchain"]["report"]["runtime"]["observability"]["langsmith"]
        self.assertEqual(langsmith["enabled"], True)
        self.assertEqual(langsmith["project"], "report-prod")
        self.assertEqual(langsmith["endpoint"], "https://api.smith.langchain.com")
        self.assertNotIn("api_key", langsmith)
        self.assertEqual(local_updates, [{"credential_updates": {"langsmith_api_key": "lsv2_pt_test"}}])

    def test_put_report_runtime_settings_stores_report_api_key_in_local_overrides(self) -> None:
        stored = {"langchain": {"report": {"runtime": {"model": {"provider": "openai", "model": "glm-5"}}}}, "credentials": {}}
        persisted = {}
        local_updates = []

        def _persist(config):
            persisted.update(config)

        client = self._client()
        with patch("server_support.settings_config.load_llm_config", side_effect=[stored, stored]), patch(
            "server_support.settings_config.persist_llm_config", side_effect=_persist
        ), patch(
            "server_support.settings_config.update_llm_local_secrets",
            side_effect=lambda **kwargs: local_updates.append(kwargs),
        ), patch(
            "server_support.settings_config._report_runtime_persistence_payload",
            return_value={"enabled": True, "status": "ready"},
        ), patch(
            "server_support.settings_config._report_runtime_observability_payload",
            return_value={"enabled": False, "project": "opinion-system-report", "endpoint": "", "api_key": {"configured": False, "last_four": ""}},
        ):
            response = client.put(
                "/api/settings/llm/report-runtime",
                json={"provider": "openai", "model": "glm-5", "api_key": "sk-report-local"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(local_updates, [{"credential_updates": {"report_api_key": "sk-report-local"}}])
        self.assertEqual(persisted["credentials"]["report_api_key"], "sk-report-local")


if __name__ == "__main__":
    unittest.main()
