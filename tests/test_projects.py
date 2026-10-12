# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from shiptally.projects import Mapper, load_config, redact


TMP = Path(__file__).resolve().parents[2] / "_jobs" / "shiptally3" / "tmp"


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout


class ProjectTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=str(TMP))
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def repo(self, name):
        path = self.root / name
        path.mkdir()
        git(path, "init", "-b", "main")
        git(path, "config", "user.name", "Test User")
        git(path, "config", "user.email", "test@example.invalid")
        git(path, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "fixture")
        return path

    def test_repository_majority_and_worktree_fold(self):
        main = self.repo("main-project")
        worktree = self.root / "other-worktree"
        git(main, "worktree", "add", "-b", "fixture-branch", str(worktree))
        nested = worktree / "src"
        nested.mkdir()
        other = self.repo("other-project")
        mapper = Mapper()
        original = mapper.resolve([str(main)])
        result = mapper.resolve([str(nested), str(worktree), str(other)])
        self.assertEqual(result["key"], original["key"])
        self.assertEqual(result["name"], "main-project")
        self.assertEqual(result["repo_paths"], [str(main)])
        self.assertEqual(result["paths"], [str(nested), str(worktree)])

    def test_weighted_cwd_records(self):
        one, two = self.repo("one"), self.repo("two")
        result = Mapper().resolve({str(one): 1, str(two): 3})
        self.assertEqual(result["name"], "two")

    def test_missing_directory_and_empty_records(self):
        result = Mapper().resolve([str(self.root / "gone" / "project")])
        self.assertEqual(result["name"], "project")
        self.assertEqual(result["repo_paths"], [])
        self.assertEqual(Mapper().resolve([])["name"], "unknown")

    def test_deleted_claude_worktree_folds_to_nearest_repository(self):
        main = self.repo("main")
        nested = main / "nested-repo"
        nested.mkdir()
        git(nested, "init", "-b", "main")
        gone = nested / ".claude" / "worktrees" / "modest-hodgkin-d22af4" / "src"
        result = Mapper().resolve([str(gone)])
        self.assertEqual(result["repo_paths"], [str(nested)])
        self.assertEqual(result["name"], "nested-repo")
        self.assertEqual(result["paths"], [str(gone)])
        self.assertEqual(result["key"], Mapper().resolve([str(nested)])["key"])

    def test_missing_non_claude_paths_keep_basename_fallback(self):
        main = self.repo("main")
        for gone in (main / "gone" / "random", self.root / "main-wt" / "random",
                     self.root / "no-repo" / ".claude" / "worktrees" / "random"):
            result = Mapper().resolve([str(gone)])
            self.assertEqual(result["name"], "random")
            self.assertEqual(result["repo_paths"], [])

    def test_home_name_never_uses_username_even_if_home_is_a_repository(self):
        home = self.repo("synthetic-user")
        with patch("shiptally.projects.Path.home", return_value=home):
            result = Mapper().resolve([str(home)])
            configured = Mapper([{"match": [str(home)], "name": home.name}]).resolve([str(home)])
        self.assertEqual(result["name"], "~ (home folder)")
        self.assertEqual(configured["name"], "~ (home folder)")
        self.assertEqual(result["repo_paths"], [])

    def test_config_rename_merge_hide_and_quoted_hash(self):
        config = self.root / "config.toml"
        config.write_text('''# project rules
[[projects]]
match = ["one", "two"] # both projects
name = "One # team"
merge = "team"
hide = true
''', encoding="utf-8")
        mapper = Mapper(load_config(config))
        one = mapper.resolve([str(self.root / "one")])
        two = mapper.resolve([str(self.root / "two")])
        self.assertEqual(one["key"], two["key"])
        self.assertEqual(one["name"], "One # team")
        self.assertTrue(one["hidden"])

    def test_config_rejects_invalid_types_and_unknown_keys(self):
        config = self.root / "config.toml"
        for text in ('[[projects]]\nmatch = "one"',
                     '[[projects]]\nmatch = ["one"]\nhide = "true"',
                     '[[projects]]\nmatch = ["one"]\nunknown = "x"',
                     '[[projects]]\nmatch = ["one"]\nname = "a"\nname = "b"'):
            config.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(config)

    def test_redaction_stable_no_mutation_or_diagnostic_leaks(self):
        private_path = str(self.root / "private-project")
        report = {"projects": [{"name": "private-project", "key": "path:" + private_path,
                                "paths": [private_path], "repo_paths": [private_path],
                                "github_repos": ["fixture/private-project"],
                                "github_public_repos": ["fixture/private-project"],
                                "github_stars": {"fixture/private-project": 4},
                                "github_unknown_repos": ["fixture/private-project"],
                                "commits": 2}],
                  "diagnostics": {"bad_lines": 2, "warnings": ["Cannot read " + private_path]}}
        hidden = redact(report)
        self.assertEqual(hidden, redact(report))
        self.assertNotIn("private-project", json.dumps(hidden))
        self.assertNotIn(private_path, json.dumps(hidden))
        self.assertEqual(report["projects"][0]["name"], "private-project")
        self.assertEqual(hidden["projects"][0]["commits"], 2)
        self.assertEqual(hidden["diagnostics"]["bad_lines"], 2)
        self.assertEqual(list(hidden["projects"][0]["github_stars"].values()), [4])
