"""Tests for deep_writer module - LLM-based section generation."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.deep_report.deep_writer import (
    DeepWriterError,
    SectionContentTooSparseError,
    _validate_content_density,
    _parse_llm_response_to_blocks,
    _build_section_writer_prompt,
)
from src.report.deep_report.schemas import CompilerSectionPlanItem


class TestDeepWriter(unittest.TestCase):
    """Tests for LLM deep writing functionality."""

    def test_parse_llm_response_extracts_json_blocks(self):
        """Test parsing LLM response with valid JSON."""
        section = CompilerSectionPlanItem(
            section_id="test-section",
            title="测试章节",
            goal="测试目标",
            target_words=300,
            source_groups=["evidence"],
        )

        raw_response = '''
```json
{
  "section_id": "test-section",
  "title": "测试章节",
  "blocks": [
    {"type": "heading", "text": "测试章节", "anchor": "test-section"},
    {"type": "paragraph", "text": "这是一个测试段落，包含足够的内容以满足密度验证要求。"},
    {"type": "list", "items": ["要点一", "要点二"]}
  ],
  "evidence_refs": ["ev-1"],
  "claim_refs": ["claim-1"]
}
```
'''

        blocks, evidence_refs, claim_refs = _parse_llm_response_to_blocks(raw_response, section)

        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["type"], "heading")
        self.assertEqual(blocks[1]["type"], "paragraph")
        self.assertIn("ev-1", evidence_refs)
        self.assertIn("claim-1", claim_refs)

    def test_parse_llm_response_handles_no_json(self):
        """Test parsing LLM response without JSON creates fallback blocks."""
        section = CompilerSectionPlanItem(
            section_id="fallback-section",
            title="Fallback章节",
            goal="fallback目标",
            target_words=200,
            source_groups=["evidence"],
        )

        raw_response = "这是没有JSON格式的纯文本响应，应该创建fallback blocks。"

        blocks, evidence_refs, claim_refs = _parse_llm_response_to_blocks(raw_response, section)

        # Should create fallback blocks
        self.assertTrue(len(blocks) >= 1)
        self.assertEqual(blocks[0]["type"], "heading")

    def test_validate_content_density_passes_with_enough_content(self):
        """Test content density validation passes with sufficient content."""
        long_text = (
            "这是一个足够长的段落内容，包含超过400个字符以满足最小内容密度要求。"
            "这里是一些额外的填充文字来确保我们达到要求的字符数。"
            "继续添加更多内容以确保测试通过。"
            "舆情分析需要深度研判，不是简单堆砌数据字段。"
            "我们要锚定现象、交代机制、点出含义。"
            "证据校准是关键：语气强度匹配证据确定性。"
            "传播视角：识别议题定义权、扩散机制、信息节奏错位。"
            "本段落继续扩充以达到四百字符的最低要求。"
            "再添加更多内容来确保测试成功。"
            "深度分析要求我们不只是罗列数据，而是要有判断性文字。"
            "每个段落必须有分析语义，不是数据堆砌。"
        ) * 3  # 确保超过400字符
        blocks = [
            {"type": "heading", "text": "标题"},
            {"type": "paragraph", "text": long_text},
            {"type": "list", "items": ["条目一的内容文字，这里也有足够长度", "条目二的内容文字，继续保持足够长度"]},
        ]

        # Should not raise
        _validate_content_density(blocks, "test-section")

    def test_validate_content_density_fails_with_sparse_content(self):
        """Test content density validation fails with insufficient content."""
        blocks = [
            {"type": "heading", "text": "标题"},
            {"type": "paragraph", "text": "太短"},
        ]

        with self.assertRaises(SectionContentTooSparseError):
            _validate_content_density(blocks, "sparse-section")


if __name__ == "__main__":
    unittest.main()