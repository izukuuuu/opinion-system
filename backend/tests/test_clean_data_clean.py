from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.clean.data_clean import clean_text_whitespace, run_clean  # noqa: E402
from src.utils.setting.paths import get_data_root  # noqa: E402


class CleanDataCleanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topic_identifier = f"clean-test-{uuid.uuid4().hex[:8]}"
        self.date = "20260424"
        self.project_root = get_data_root() / "projects" / self.topic_identifier
        self.merge_root = self.project_root / "merge" / self.date
        self.clean_root = self.project_root / "clean" / self.date
        self.merge_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_clean_text_whitespace_removes_invalid_utf8_codepoints(self) -> None:
        self.assertEqual(clean_text_whitespace("A\ud800B"), "AB")

    def test_run_clean_replaces_invalid_utf8_characters_with_empty_text(self) -> None:
        target = self.merge_root / "微博.jsonl"
        record = {
            "content": "正文\ud800文本",
            "title": "标题\ud800",
            "author": "作者\ud800",
            "url": "https://example.com/\ud800",
            "published_at": "2026-04-24 10:00:00",
            "region": "江苏\ud800",
            "hit_words": "控烟\ud800",
            "polarity": "中性\ud800",
            "like_count": 1,
            "comment_count": 2,
            "favorite_count": 3,
            "share_count": 4,
        }
        with target.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(record))
            stream.write("\n")

        success = run_clean(self.topic_identifier, self.date)

        self.assertTrue(success)
        output = self.clean_root / "微博.jsonl"
        self.assertTrue(output.exists())
        rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["contents"], "title: 标题 content: 正文文本")
        self.assertEqual(row["title"], "正文文本")
        self.assertEqual(row["author"], "作者")
        self.assertEqual(row["url"], "https://example.com/")
        self.assertEqual(row["region"], "江苏省")
        self.assertEqual(row["hit_words"], "控烟")
        self.assertEqual(row["polarity"], "中性")


if __name__ == "__main__":
    unittest.main()
