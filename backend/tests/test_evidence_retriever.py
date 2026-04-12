from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.evidence_retriever import (
    analyze_temporal_event_window,
    iter_filtered_records,
    resolve_source_scope,
    search_raw_records,
    summarize_source_scope,
    verify_claim_with_records,
)
from src.utils.setting.paths import get_data_root


class EvidenceRetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topic_identifier = f"retrieval-test-{uuid.uuid4().hex[:8]}"
        self.project_root = get_data_root() / "projects" / self.topic_identifier
        self.fetch_root = self.project_root / "fetch" / "2025-01-15_2025-12-31"
        self.fetch_root.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "title": "市卫健委发布公共场所控烟新规",
                "contents": "市卫健委发布控烟政策通知，要求加强公共场所禁烟执法。",
                "platform": "新闻",
                "author": "城市日报",
                "published_at": "2025-08-20T08:00:00",
                "url": "https://example.com/policy-1",
                "source_type": "official_media",
            },
            {
                "title": "市卫健委发布公共场所控烟新规",
                "contents": "转载：市卫健委发布控烟政策通知，要求加强公共场所禁烟执法。",
                "platform": "新闻",
                "author": "城市日报转载",
                "published_at": "2025-08-20T09:00:00",
                "url": "https://example.com/policy-1",
            },
            {
                "title": "厨房总散味？文火神器助你轻松控烟",
                "contents": "厨房油烟困扰多，抽油烟机和文火神器助你轻松控烟。",
                "platform": "视频",
                "author": "家居小店",
                "published_at": "2025-08-21T10:00:00",
                "url": "https://example.com/kitchen-1",
            },
            {
                "title": "网传市卫健委发布控烟通知系谣言",
                "contents": "该消息为网传不实信息，通知截图系误读，官方未发布。",
                "platform": "微博",
                "author": "辟谣号",
                "published_at": "2025-08-22T11:00:00",
                "url": "https://example.com/rumor-1",
            },
            {
                "title": "执法部门开展控烟专项行动",
                "contents": "公共场所控烟执法专项行动启动，重点整治室内吸烟行为。",
                "platform": "新闻",
                "author": "晚报",
                "published_at": "2025-08-25T09:30:00",
                "url": "https://example.com/policy-2",
            },
            {
                "title": "世界无烟日前宣传活动升温",
                "contents": "无烟日宣传活动提前预热，社区和学校同步开展健康倡议。",
                "platform": "新闻",
                "author": "健康频道",
                "published_at": "2025-05-28T09:00:00",
                "url": "https://example.com/day-1",
            },
        ]
        with (self.fetch_root / "总体.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_search_uses_covering_fetch_range_and_suppresses_kitchen_noise(self) -> None:
        payload = search_raw_records(
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            query="控烟 政策",
            top_k=3,
        )
        self.assertEqual(payload["source_resolution"], "covering_fetch_range")
        self.assertGreater(payload["matched_records"], 0)
        self.assertLess(payload["deduped_count"], payload["candidate_count"])
        self.assertIn("控烟新规", str(payload["items"][0]["title"]))
        self.assertNotIn("厨房", str(payload["items"][0]["title"]))

    def test_verify_claim_returns_conflicting_when_support_and_refute_coexist(self) -> None:
        payload = verify_claim_with_records(
            topic_identifier=self.topic_identifier,
            start="2025-08-01",
            end="2025-08-31",
            claim="市卫健委发布控烟通知",
            top_k=6,
        )
        self.assertEqual(payload["verification_status"], "conflicting")
        self.assertTrue(payload["supporting_items"])
        self.assertTrue(payload["contradicting_items"])

    def test_temporal_and_scope_helpers_return_non_empty_results(self) -> None:
        temporal = analyze_temporal_event_window(
            topic_identifier=self.topic_identifier,
            start="2025-01-15",
            end="2025-12-31",
            anchor_date="2025-08-22",
            query="控烟",
            window_days=5,
            top_k=4,
        )
        scope = summarize_source_scope(
            topic_identifier=self.topic_identifier,
            start="2025-01-15",
            end="2025-12-31",
        )
        self.assertEqual(temporal["verification_status"], "ok")
        self.assertGreaterEqual(temporal["windows"]["anchor_window"]["count"], 1)
        self.assertTrue(scope["platforms"])
        self.assertEqual(scope["source_resolution"], "exact_fetch_range")

    def test_overlap_fetch_range_is_accepted_and_filtered_by_requested_window(self) -> None:
        resolution = resolve_source_scope(self.topic_identifier, "2025-01-01", "2025-06-30")
        rows = list(
            iter_filtered_records(
                topic_identifier=self.topic_identifier,
                start="2025-01-01",
                end="2025-06-30",
            )
        )

        self.assertEqual(resolution["source_resolution"], "overlap_fetch_range")
        self.assertEqual(resolution["resolved_fetch_range"]["start"], "2025-01-15")
        self.assertEqual(resolution["resolved_fetch_range"]["end"], "2025-12-31")
        self.assertTrue(rows)
        self.assertTrue(all(str(row.get("published_at") or "")[:10] <= "2025-06-30" for row in rows))


if __name__ == "__main__":
    unittest.main()
