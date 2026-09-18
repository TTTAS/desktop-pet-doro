"""Repo-map tests run with unittest and no app dependencies."""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("repo_map", ROOT / "scripts/repo_map.py")
repo_map = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repo_map)


class RepoMapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.write("doro.py", "from doro_app.alpha import Alpha\n")
        self.write(
            "doro_app/alpha.py",
            "from .beta import helper\nclass Alpha:\n    def run(self, value: int = 1) -> str:\n        return str(value)\n",
        )
        self.write(
            "doro_app/beta.py",
            "def helper():\n    return 1\nraise RuntimeError('must not execute')\n",
        )
        self.write("tests/test_alpha.py", "")
        self.write(
            "docs/ai/areas.json",
            json.dumps(
                [
                    {
                        "id": "alpha",
                        "name": "測試模組",
                        "aliases": ["範例"],
                        "scope": ["doro.py", "doro_app/*.py"],
                        "entries": ["doro_app/alpha.py"],
                        "tests": ["tests/test_alpha.py"],
                        "purpose": "Test navigation.",
                    }
                ]
            ),
        )

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def data(self):
        files = repo_map.scan(self.root)
        return files, repo_map.load_areas(self.root, files)

    def test_signatures_imports_and_no_execution(self):
        files, areas = self.data()
        self.assertEqual(files["doro_app/alpha.py"]["imports"], ["doro_app/beta.py"])
        text = repo_map.focused(files, areas, "Alpha.run", 5000)
        self.assertIn("L3: `Alpha.run(self, value: int=1) -> str`", text)
        self.assertLess(text.index("## doro_app/alpha.py"), text.index("## doro.py"))
        self.assertIn("tests/test_alpha.py", text)

    def test_alias_windows_path_and_budget(self):
        files, areas = self.data()
        for query in ("範例", "doro_app\\alpha.py", "Alpha"):
            text = repo_map.focused(files, areas, query, 512)
            self.assertLessEqual(len(text), 512)
            self.assertIn("alpha.py", text)
        self.assertIn("已省略", repo_map.bounded("long line\n" * 1000, 512))

    def test_unknown_and_empty_queries_fail(self):
        files, areas = self.data()
        for query in ("does_not_exist", "  "):
            with self.assertRaises(ValueError):
                repo_map.focused(files, areas, query, 1000)

    def test_map_detects_interface_changes_but_not_body_or_line_shifts(self):
        files, areas = self.data()
        before = repo_map.summary(files, areas)
        self.write("doro_app/beta.py", "\n\ndef helper():\n    return 2\n")
        self.assertEqual(before, repo_map.summary(*self.data()))
        self.write("doro_app/beta.py", "def helper(argument):\n    return argument\n")
        self.assertNotEqual(before, repo_map.summary(*self.data()))

    def test_unmapped_source_and_missing_test_are_errors(self):
        self.write("doro_app/new/feature.py", "class New: pass\n")
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            self.data()
        (self.root / "doro_app/new/feature.py").unlink()
        (self.root / "tests/test_alpha.py").unlink()
        with self.assertRaisesRegex(ValueError, "missing test"):
            self.data()

    def test_resources_are_excluded(self):
        self.write("doro_app/res/private.py", "not valid python!")
        files, _ = self.data()
        self.assertNotIn("doro_app/res/private.py", files)

    def test_write_and_stale_check(self):
        with patch.object(repo_map, "ROOT", self.root):
            self.assertEqual(repo_map.main(["--write"]), 0)
            self.assertEqual(repo_map.main(["--check"]), 0)
            self.write("doro_app/new.py", "class Added: pass\n")
            self.assertEqual(repo_map.main(["--check"]), 1)

    def test_navigation_links_resolve(self):
        for relative in (
            "AGENTS.md",
            "CLAUDE.md",
            "docs/INDEX.md",
            "docs/REPO_MAP.md",
            "docs/ai/WORKFLOW.md",
            "docs/ai/FEATURE_GUIDE.md",
        ):
            document = ROOT / relative
            text = document.read_text(encoding="utf-8-sig")
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in link or link.startswith("#"):
                    continue
                self.assertTrue(
                    (document.parent / link.split("#")[0]).exists(), f"{relative}: {link}"
                )


if __name__ == "__main__":
    unittest.main()
