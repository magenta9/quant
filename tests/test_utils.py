import json
import shutil
import unittest
from pathlib import Path

from core.utils import (
    ANNUALIZATION_FACTORS,
    ensure_directory,
    generate_run_id,
    write_json,
    write_markdown,
)


class UtilsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path("test_artifacts")
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def test_ensure_directory_and_writers_create_parent_paths(self) -> None:
        json_path = self.workspace / "runs" / "sample" / "macro_view.json"
        markdown_path = self.workspace / "runs" / "sample" / "memo.md"

        ensure_directory(json_path.parent)
        write_json(json_path, {"regime": "late_cycle"})
        write_markdown(markdown_path, "# Memo\n")

        self.assertTrue(json_path.exists())
        self.assertEqual(json.loads(json_path.read_text())["regime"], "late_cycle")
        self.assertEqual(markdown_path.read_text(), "# Memo\n")

    def test_generate_run_id_uses_utc_timestamp_prefix(self) -> None:
        run_id = generate_run_id()
        self.assertRegex(run_id, r"^run-\d{8}T\d{6}Z-[0-9a-f]{8}$")

    def test_annualization_factors_cover_daily_monthly_and_quarterly(self) -> None:
        self.assertEqual(ANNUALIZATION_FACTORS["daily"], 252)
        self.assertEqual(ANNUALIZATION_FACTORS["monthly"], 12)
        self.assertEqual(ANNUALIZATION_FACTORS["quarterly"], 4)


if __name__ == "__main__":
    unittest.main()
