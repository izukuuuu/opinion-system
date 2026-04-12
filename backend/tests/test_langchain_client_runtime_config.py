from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.ai.langchain_client import _resolve_client_config


class LangchainClientRuntimeConfigTests(unittest.TestCase):
    def test_report_task_prefers_canonical_runtime_model(self) -> None:
        llm_config = {
            "langchain": {
                "provider": "qwen",
                "model": "qwen3.5-plus",
                "report_model": "qwen3.5-plus",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "report": {
                    "runtime": {
                        "model": {
                            "provider": "openai",
                            "model": "glm-5",
                            "base_url": "https://coding.dashscope.aliyuncs.com/v1",
                            "temperature": 0.2,
                            "max_tokens": 18000,
                            "timeout": 420.0,
                            "max_retries": 2,
                        }
                    }
                },
            },
            "credentials": {
                "report_api_key": "sk-report",
                "qwen_api_key": "sk-qwen",
            },
        }

        with patch("src.utils.ai.langchain_client.settings.get_llm_config", return_value=llm_config):
            client_cfg = _resolve_client_config(task="report", model_role="report", temperature=0.15, max_tokens=4200)

        self.assertIsNotNone(client_cfg)
        self.assertEqual(client_cfg["provider"], "openai")
        self.assertEqual(client_cfg["model"], "glm-5")
        self.assertEqual(client_cfg["base_url"], "https://coding.dashscope.aliyuncs.com/v1")
        self.assertEqual(client_cfg["api_key"], "sk-report")


if __name__ == "__main__":
    unittest.main()
