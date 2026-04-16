from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.media_tagging.service import (  # noqa: E402
    REGISTRY_PATH,
    build_labeled_media_payload,
    list_registry_items,
    run_media_tagging,
    save_media_registry,
    update_media_tagging_labels,
)
from src.utils.setting.paths import get_data_root  # noqa: E402


class MediaTaggingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topic_identifier = f"media-test-{uuid.uuid4().hex[:8]}"
        self.start = "2025-01-01"
        self.end = "2025-01-07"
        self.project_root = get_data_root() / "projects" / self.topic_identifier
        self.fetch_root = self.project_root / "fetch" / f"{self.start}_{self.end}"
        self.fetch_root.mkdir(parents=True, exist_ok=True)
        self.registry_backup = REGISTRY_PATH.read_text(encoding="utf-8") if REGISTRY_PATH.exists() else None
        self._write_fetch_records(
            [
                {
                    "publisher": "人民日报",
                    "platform": "news",
                    "title": "样本一",
                    "url": "https://example.com/1",
                    "published_at": "2025-01-03T10:00:00+08:00",
                },
                {
                    "author": "人民日报",
                    "platform": "news",
                    "title": "样本二",
                    "url": "https://example.com/2",
                    "published_at": "2025-01-04T10:00:00+08:00",
                },
                {
                    "publisher": "北京日报",
                    "platform": "news",
                    "title": "样本三",
                    "url": "https://example.com/3",
                    "published_at": "2025-01-02T08:00:00+08:00",
                },
            ]
        )
        save_media_registry(
            [
                {
                    "id": "mr-people",
                    "name": "人民日报社",
                    "aliases": ["人民日报"],
                    "media_level": "official_media",
                    "status": "active",
                    "notes": "测试别名命中",
                }
            ]
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.project_root, ignore_errors=True)
        if self.registry_backup is None:
            if REGISTRY_PATH.exists():
                REGISTRY_PATH.unlink()
        else:
            REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            REGISTRY_PATH.write_text(self.registry_backup, encoding="utf-8")

    def _write_fetch_records(self, records: list[dict]) -> None:
        target = self.fetch_root / "总体.jsonl"
        with target.open("w", encoding="utf-8") as stream:
            for item in records:
                stream.write(json.dumps(item, ensure_ascii=False))
                stream.write("\n")

    def test_run_media_tagging_sorts_candidates_and_matches_alias(self) -> None:
        payload = run_media_tagging(self.topic_identifier, self.start, end_date=self.end)

        self.assertEqual(payload["status"], "ok")
        candidates = payload["candidates"]
        self.assertEqual(candidates[0]["publisher_name"], "人民日报")
        self.assertEqual(candidates[0]["publish_count"], 2)
        self.assertEqual(candidates[0]["matched_registry_name"], "人民日报社")
        self.assertEqual(candidates[0]["current_label"], "official_media")
        self.assertGreaterEqual(candidates[0]["publish_count"], candidates[1]["publish_count"])

    def test_update_labels_and_build_labeled_payload_only_returns_labeled_media(self) -> None:
        run_media_tagging(self.topic_identifier, self.start, end_date=self.end)

        refreshed = update_media_tagging_labels(
            self.topic_identifier,
            self.start,
            end_date=self.end,
            updates=[
                {
                    "publisher_name": "北京日报",
                    "current_label": "local_media",
                }
            ],
        )

        updated_candidates = refreshed["candidates"]
        beijing = next(item for item in updated_candidates if item["publisher_name"] == "北京日报")
        self.assertEqual(beijing["current_label"], "local_media")

        labeled_payload = build_labeled_media_payload(
            self.topic_identifier,
            self.start,
            end_date=self.end,
        )
        self.assertEqual(len(labeled_payload["official_media"]), 1)
        self.assertEqual(len(labeled_payload["local_media"]), 1)
        self.assertEqual(len(labeled_payload["all_labeled_media"]), 2)
        self.assertTrue(
            all(item["media_level"] in {"official_media", "local_media"} for item in labeled_payload["all_labeled_media"])
        )

        registry_names = {item["name"] for item in list_registry_items()}
        self.assertIn("北京日报", registry_names)


if __name__ == "__main__":
    unittest.main()
