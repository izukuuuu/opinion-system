from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.setting.paths import get_data_root


class SettingPathsTests(unittest.TestCase):
    def test_get_data_root_does_not_append_backend_when_project_root_is_backend(self) -> None:
        backend_root = Path(r"F:\opinion-system\backend")
        with patch("src.utils.setting.paths.get_project_root", return_value=backend_root):
            data_root = get_data_root()
        self.assertEqual(data_root, backend_root / "data")


if __name__ == "__main__":
    unittest.main()
