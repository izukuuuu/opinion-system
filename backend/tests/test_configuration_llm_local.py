from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server_support.configuration import load_llm_config


class LlmLocalConfigTests(unittest.TestCase):
    def test_load_llm_config_merges_static_local_and_dynamic_credentials(self) -> None:
        static_config = {
            "langchain": {"provider": "qwen"},
            "credentials": {
                "openai_api_key": "",
                "openai_base_url": "",
                "qwen_api_key": "",
                "report_api_key": "",
            },
        }
        local_config = {
            "credentials": {
                "openai_api_key": "sk-local-openai",
                "openai_base_url": "https://local.example/v1",
                "qwen_api_key": "sk-local-qwen",
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


if __name__ == "__main__":
    unittest.main()
