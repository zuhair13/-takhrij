from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_corpus_boundary import (
    find_build_context_gaps,
    find_tracked_leaks,
    find_workspace_leaks,
)

ROOT = Path(__file__).resolve().parents[1]


class CorpusBoundaryTests(unittest.TestCase):
    def test_repository_build_and_tracking_boundaries_are_clean(self):
        self.assertEqual(find_tracked_leaks(ROOT), [])
        self.assertEqual(find_build_context_gaps(ROOT), [])

    def test_workspace_scan_detects_database_and_openiti_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "leaked.db").write_bytes(b"SQLite format 3\x00" + b"x" * 20)
            (root / "leaked.mARkdown").write_bytes(b"######OpenITI#\nsynthetic leak test")
            findings = find_workspace_leaks(root)
        self.assertTrue(any("SQLite database" in finding for finding in findings))
        self.assertTrue(any("OpenITI content" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
