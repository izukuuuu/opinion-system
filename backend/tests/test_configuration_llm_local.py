from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server_support.configuration import load_llm_config, persist_llm_config


class LlmLocalConfigTests(unittest.TestCase):
    def test_load_llm_config_merges_static_local_and_dynamic_credentials(self) -> None:
        static_config = {
            "langchain": {"provider": "qwen"},
            "credentials": {
                "openai_api_key": "",
                "openai_base_url": "",
                "qwen_api_key": "",
                "report_api_key": "",
                "langsmith_api_key": "",
            },
        }
        local_config = {
            "credentials": {
                "openai_api_key": "sk-local-openai",
                "openai_base_url": "https://local.example/v1",
                "qwen_api_key": "sk-local-qwen",
                "langsmith_api_key": "lsv2-local-langsmith",
            }
        }
        dynamic_config = {"credentials": {"report_api_key": "sk-dynamic-report"}}

        with patch("server_support.configuration._load_static_llm_config", return_value=static_config), patch(
            "server_support.configuration._load_local_llm_config", return_value=local_config
        ), patch("server_support.configuration.load_settings_config", return_value=dynamic_config):
            config = load_llm_config()

        self.assertEqual(config["credentials"]["openai_api_key"], "sk-local-openai")
        self.assertEqual(config["credentials"]["openai_base_url"], "https://local.example/v1")
        self.assertEqual(config["credentials"]["qwen_api_key"], "sk-local-qwen")
        self.assertEqual(config["credentials"]["report_api_key"], "sk-dynamic-report")
        self.assertEqual(config["credentials"]["langsmith_api_key"], "lsv2-local-langsmith")

    def test_load_llm_config_keeps_local_secret_when_dynamic_value_is_blank(self) -> None:
        static_config = {
            "credentials": {
                "report_api_key": "",
                "openai_api_key": "",
                "openai_base_url": "",
            }
        }
        local_config = {
            "credentials": {
                "report_api_key": "sk-local-report",
                "openai_api_key": "sk-local-openai",
                "openai_base_url": "https://local.example/v1",
            }
        }
        dynamic_config = {
            "credentials": {
                "report_api_key": "",
                "openai_api_key": "",
                "openai_base_url": "",
            }
        }

        with patch("server_support.configuration._load_static_llm_config", return_value=static_config), patch(
            "server_support.configuration._load_local_llm_config", return_value=local_config
        ), patch("server_support.configuration.load_settings_config", return_value=dynamic_config):
            config = load_llm_config()

        self.assertEqual(config["credentials"]["report_api_key"], "sk-local-report")
        self.assertEqual(config["credentials"]["openai_api_key"], "sk-local-openai")
        self.assertEqual(config["credentials"]["openai_base_url"], "https://local.example/v1")

    def test_persist_llm_config_strips_local_only_secrets_from_tracked_payload(self) -> None:
        merged_config = {
            "langchain": {
                "report": {
                    "runtime": {
                        "observability": {
                            "langsmith": {
                                "enabled": True,
                                "project": "Opinion System",
                                "api_key": "lsv2_pt_secret",
                            }
                        }
                    }
                }
            },
            "credentials": {
                "openai_api_key": "sk-openai",
                "qwen_api_key": "sk-qwen",
                "report_api_key": "sk-report",
                "langsmith_api_key": "lsv2-secret",
                "openai_base_url": "https://api.example.com/v1",
            },
        }
        persisted = {}

        with patch("server_support.configuration.save_settings_config", side_effect=lambda name, data: persisted.update(data)), patch(
            "server_support.configuration.reload_settings"
        ):
            persist_llm_config(merged_config)

        self.assertEqual(persisted["credentials"]["openai_base_url"], "https://api.example.com/v1")
        self.assertNotIn("openai_api_key", persisted["credentials"])
        self.assertNotIn("qwen_api_key", persisted["credentials"])
        self.assertNotIn("report_api_key", persisted["credentials"])
        self.assertNotIn("langsmith_api_key", persisted["credentials"])
        langsmith = persisted["langchain"]["report"]["runtime"]["observability"]["langsmith"]
        self.assertNotIn("api_key", langsmith)


if __name__ == "__main__":
    unittest.main()
