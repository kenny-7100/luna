"""Check that doctor reports real missing and empty entries without creating them."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from luna.cli import REQUIRED_DIRECTORIES, REQUIRED_FILES, check_project, main


class DoctorTests(unittest.TestCase):
    def test_reports_missing_entries_without_creating_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(check_project(root))
            self.assertEqual(main(["doctor", "--root", directory]), 1)
            self.assertEqual(list(root.iterdir()), [])

    def test_valid_structure_and_empty_document_detection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in REQUIRED_DIRECTORIES:
                (root / name).mkdir(parents=True, exist_ok=True)
            for name in REQUIRED_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("content\n", encoding="utf-8")
            self.assertEqual(check_project(root), [])
            (root / "AGENTS.md").write_text(" \n", encoding="utf-8")
            self.assertIn("缺少文件或内容为空：AGENTS.md", check_project(root))


if __name__ == "__main__":
    unittest.main()
