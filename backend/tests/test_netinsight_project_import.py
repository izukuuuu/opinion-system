from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.netinsight import task_queue  # noqa: E402
from src.project import storage as project_storage  # noqa: E402
from src.project.manager import ProjectManager  # noqa: E402


class NetInsightProjectImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_root = self.root / "data"
        self.manager = ProjectManager(storage_dir=self.data_root)
        self.project = self.manager.create_or_update_project("采集专题")

        self._old_task_roots = (
            task_queue.STATE_ROOT,
            task_queue.TASK_STATE_DIR,
            task_queue.WORKER_STATUS_PATH,
            task_queue.LOGIN_STATE_PATH,
            task_queue.SESSION_STATE_PATH,
            task_queue.get_data_root,
            task_queue.get_project_manager,
        )
        self._old_storage_roots = (
            project_storage._DATA_ROOT,
            project_storage._REPO_ROOT,
            project_storage.get_project_manager,
        )

        task_queue.STATE_ROOT = self.data_root / "_netinsight"
        task_queue.TASK_STATE_DIR = task_queue.STATE_ROOT / "tasks"
        task_queue.WORKER_STATUS_PATH = task_queue.STATE_ROOT / "worker.json"
        task_queue.LOGIN_STATE_PATH = task_queue.STATE_ROOT / "login_state.json"
        task_queue.SESSION_STATE_PATH = task_queue.STATE_ROOT / "session_state.json"
        task_queue.get_data_root = lambda: self.data_root
        task_queue.get_project_manager = lambda: self.manager

        project_storage._DATA_ROOT = self.data_root / "projects"
        project_storage._REPO_ROOT = self.root
        project_storage.get_project_manager = lambda: self.manager

    def tearDown(self) -> None:
        (
            task_queue.STATE_ROOT,
            task_queue.TASK_STATE_DIR,
            task_queue.WORKER_STATUS_PATH,
            task_queue.LOGIN_STATE_PATH,
            task_queue.SESSION_STATE_PATH,
            task_queue.get_data_root,
            task_queue.get_project_manager,
        ) = self._old_task_roots
        (
            project_storage._DATA_ROOT,
            project_storage._REPO_ROOT,
            project_storage.get_project_manager,
        ) = self._old_storage_roots
        self.tmp.cleanup()

    def _create_completed_task(self, *, write_csv: bool = True) -> dict:
        task = task_queue.create_task(
            {
                "title": "采集任务",
                "project": "采集专题",
                "keywords": ["控烟"],
                "platforms": ["微博"],
                "start_date": "2026-05-01",
                "end_date": "2026-05-15",
                "auto_import_project": True,
            }
        )
        output_dir = task_queue.output_dir_for_task(task)
        csv_path = output_dir / "records.csv"
        jsonl_path = output_dir / "records.jsonl"
        meta_path = output_dir / "meta.json"
        if write_csv:
            csv_path.write_text(
                "任务ID,检索词,平台,标题,内容,作者,发布时间\n"
                f"{task['id']},控烟,微博,标题A,正文A,作者A,2026-05-10 12:00:00\n",
                encoding="utf-8-sig",
            )
            jsonl_path.write_text("", encoding="utf-8")
            meta_path.write_text("{}", encoding="utf-8")
        return task_queue.mark_task_completed(
            task["id"],
            {
                "dir": str(output_dir),
                "files": [str(csv_path), str(jsonl_path), str(meta_path)] if write_csv else [],
                "record_count": 1 if write_csv else 0,
                "deduplicated_count": 1 if write_csv else 0,
                "removed_duplicates": 0,
            },
            "采集完成",
        )

    def test_import_completed_task_output_to_project_dataset(self) -> None:
        task = self._create_completed_task()

        result = task_queue.import_task_output_to_project(task["id"])

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["dataset_id"])
        dataset = result["dataset"]
        self.assertEqual(dataset["project"], "采集专题")
        self.assertEqual(dataset["rows"], 1)
        self.assertEqual(dataset["column_mapping"]["date"], "发布时间")
        self.assertEqual(dataset["column_mapping"]["title"], "标题")
        self.assertEqual(dataset["column_mapping"]["content"], "内容")
        self.assertEqual(dataset["column_mapping"]["author"], "作者")

    def test_import_failure_is_recorded_without_losing_task_output(self) -> None:
        task = self._create_completed_task(write_csv=False)

        with self.assertRaises(Exception):
            task_queue.import_task_output_to_project(task["id"])

        updated = task_queue.get_task(task["id"])
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["output"]["project_import"]["status"], "failed")
        self.assertIn("message", updated["output"]["project_import"])


if __name__ == "__main__":
    unittest.main()
