# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from shiptally import git_stats


TMP = Path(__file__).resolve().parents[2] / "_jobs" / "shiptally3" / "tmp"


def git(path, *args, env=None):
    return subprocess.run(["git", "-C", str(path), *args], check=True, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout


class GitStatsTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=str(TMP))
        self.path = Path(self.temp.name) / "fixture"
        self.path.mkdir()
        git(self.path, "init", "-b", "main")
        git(self.path, "config", "user.name", "Fixture Author")
        git(self.path, "config", "user.email", "test@example.invalid")
        self.commit("one\ntwo\n", "2026-01-01T12:00:00+00:00", "First Author")
        self.commit("one\nthree\nfour\n", "2026-01-02T12:00:00+00:00", "Second Author")

    def tearDown(self):
        self.temp.cleanup()

    def commit(self, content, date, author, email="test@example.invalid"):
        (self.path / "file.txt").write_text(content, encoding="utf-8")
        git(self.path, "add", "file.txt")
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date,
                   GIT_AUTHOR_NAME=author, GIT_AUTHOR_EMAIL=email)
        git(self.path, "-c", "commit.gpgsign=false", "commit", "-m", "fixture", env=env)

    def test_all_authors_line_changes_and_date_window(self):
        all_stats = git_stats.collect([str(self.path)])
        self.assertEqual((all_stats["commits"], all_stats["lines_added"],
                          all_stats["lines_removed"]), (2, 4, 1))
        stats = git_stats.collect([str(self.path)], "2026-01-02", "2026-01-02")
        self.assertEqual((stats["commits"], stats["lines_added"], stats["lines_removed"]), (1, 2, 1))

    def test_author_and_exact_timestamp_boundaries(self):
        self.assertEqual(git_stats.collect([self.path], author="First Author")["commits"], 1)
        stats = git_stats.collect([self.path], "2026-01-02T12:00:00Z", "2026-01-02T12:00:00Z")
        self.assertEqual(stats["commits"], 1)
        stats = git_stats.collect([self.path], "2026-01-02T12:00:01Z", None)
        self.assertEqual(stats["commits"], 0)

    def test_default_exact_email_excludes_upstream_and_counts_only_own_lines(self):
        self.commit("upstream\n" * 50, "2026-01-03T12:00:00Z", "Upstream",
                    "other@example.invalid")
        self.commit("lookalike\n", "2026-01-04T12:00:00Z", "Lookalike",
                    "prefix-test@example.invalid")
        stats = git_stats.collect([self.path])
        self.assertEqual((stats["commits"], stats["lines_added"], stats["lines_removed"]), (2, 4, 1))
        self.assertIn("Exact author email", stats["author_rule"])
        self.assertEqual(git_stats.collect([self.path], all_authors=True)["commits"], 4)
        explicit = git_stats.collect([self.path], author="Upstream")
        self.assertEqual((explicit["commits"], explicit["lines_added"], explicit["lines_removed"]), (1, 50, 3))
        self.assertEqual(explicit["author_rule"], "Git --author pattern: Upstream")

    def test_global_email_fallback_local_override_and_missing_email(self):
        config = self.path.parent / "global.gitconfig"
        config.write_text('[user]\nemail = test@example.invalid\n', encoding="utf-8")
        with patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}):
            git(self.path, "config", "--local", "--unset", "user.email")
            self.assertEqual(git_stats.collect([self.path])["commits"], 2)
            git(self.path, "config", "--local", "user.email", "other@example.invalid")
            self.assertEqual(git_stats.collect([self.path])["commits"], 0)
            git(self.path, "config", "--local", "--unset", "user.email")
            config.write_text("", encoding="utf-8")
            stats = git_stats.collect([self.path])
            self.assertEqual(stats["commits"], 0)
            self.assertEqual(stats["missing_author_emails"], 1)
            self.assertEqual(git_stats.collect([self.path], all_authors=True)["commits"], 2)

    def test_worktree_deduplication_and_all_branch_history(self):
        other = self.path.parent / "worktree"
        git(self.path, "worktree", "add", "-b", "fixture-branch", str(other))
        (other / "branch.txt").write_text("branch\n", encoding="utf-8")
        git(other, "add", "branch.txt")
        git(other, "-c", "commit.gpgsign=false", "commit", "-m", "branch")
        stats = git_stats.collect([self.path, other])
        self.assertEqual(stats["repo_count"], 1)
        self.assertEqual(stats["commits"], 3)
        self.assertEqual(stats["lines_added"], 5)

    def test_binary_files_are_not_line_counts(self):
        (self.path / "binary.bin").write_bytes(b"\x00\x01\x02")
        git(self.path, "add", "binary.bin")
        git(self.path, "-c", "commit.gpgsign=false", "commit", "-m", "binary")
        stats = git_stats.collect([self.path])
        self.assertEqual(stats["commits"], 3)
        self.assertEqual(stats["lines_added"], 4)

    def test_empty_repository_and_missing_directory(self):
        empty = self.path.parent / "empty"
        empty.mkdir()
        git(empty, "init", "-b", "main")
        stats = git_stats.collect([empty, self.path.parent / "gone"])
        self.assertEqual(stats["repo_count"], 1)
        self.assertEqual(stats["commits"], 0)

    def test_github_remote_is_not_proof_public_and_no_default_network(self):
        git(self.path, "remote", "add", "origin", "git@github.com:fixture/example.git")
        with patch.object(git_stats, "_github_metadata") as fetch:
            stats = git_stats.collect([self.path])
            fetch.assert_not_called()
        self.assertTrue(stats["github_remote"])
        self.assertEqual(stats["github_repos"], ["fixture/example"])
        self.assertIsNone(stats["public"])
        self.assertIsNone(stats["stars"])

    def test_github_opt_in_metadata_and_failure_unknown(self):
        git(self.path, "remote", "add", "origin", "https://github.com/fixture/example.git")
        with patch.object(git_stats, "_github_metadata", return_value={"public": True, "stars": 8}):
            stats = git_stats.collect([self.path], github=True)
        self.assertTrue(stats["public"])
        self.assertEqual(stats["stars"], 8)
        self.assertEqual(stats["github_stars"], {"fixture/example": 8})
        self.assertEqual(stats["github_public_repos"], ["fixture/example"])
        with patch.object(git_stats, "_github_metadata", return_value=None):
            stats = git_stats.collect([self.path], github=True)
        self.assertIsNone(stats["public"])
        self.assertIsNone(stats["stars"])
        self.assertEqual(stats["github_unknown_repos"], ["fixture/example"])

    def test_shared_github_cache_and_partial_metadata(self):
        git(self.path, "remote", "add", "origin", "https://github.com/fixture/example.git")
        git(self.path, "remote", "add", "other", "https://github.com/fixture/missing.git")
        cache = {}
        with patch.object(git_stats, "_github_metadata", side_effect=[{"public": True, "stars": 8}, None]) as fetch:
            stats = git_stats.collect([self.path], github=True, metadata_cache=cache)
            git_stats.collect([self.path], github=True, metadata_cache=cache)
            self.assertEqual(fetch.call_count, 2)
        self.assertTrue(stats["public"])
        self.assertIsNone(stats["stars"])
        self.assertEqual(stats["github_unknown_repos"], ["fixture/missing"])
        self.assertEqual(stats["github_stars"], {"fixture/example": 8})

    def test_github_url_parser_requires_exact_hostname(self):
        self.assertIsNone(git_stats._github_name("https://evilgithub.com/fixture/example.git"))
        for value in ("https://github.com/fixture/example.git", "ssh://git@github.com/fixture/example.git", "git@github.com:fixture/example.git"):
            self.assertEqual(git_stats._github_name(value), "fixture/example")

    def test_failed_git_log_is_unknown_not_zero(self):
        with patch.object(git_stats, "_run", side_effect=["test@example.invalid", None, None, ""]):
            stats = git_stats.collect([self.path])
        self.assertIsNone(stats["commits"])
        self.assertIsNone(stats["lines_added"])
        self.assertIsNone(stats["lines_removed"])
        self.assertEqual(stats["git_errors"], 1)

    def test_failed_log_nonempty_repository_is_unknown(self):
        with patch.object(git_stats, "_run", side_effect=["test@example.invalid", None, "2\n", None]):
            stats = git_stats.collect([self.path])
        self.assertIsNone(stats["commits"])
        self.assertEqual(stats["git_errors"], 1)

    def test_failed_log_confirmed_empty_repository_is_zero(self):
        with patch.object(git_stats, "_run", side_effect=["test@example.invalid", None, "0\n", ""]):
            stats = git_stats.collect([self.path])
        self.assertEqual(stats["commits"], 0)
        self.assertEqual(stats["lines_added"], 0)
        self.assertEqual(stats["git_errors"], 0)

    def test_one_failed_repository_makes_merged_git_counts_unknown(self):
        empty = self.path.parent / "another"
        empty.mkdir()
        git(empty, "init", "-b", "main")
        with patch.object(git_stats, "_run", side_effect=["test@example.invalid", "", "", "test@example.invalid", None, None, ""]):
            stats = git_stats.collect([self.path, empty])
        self.assertEqual(stats["repo_count"], 2)
        self.assertIsNone(stats["commits"])
        self.assertEqual(stats["git_errors"], 1)

class GithubTransportTests(unittest.TestCase):
    def test_gh_api_has_ten_second_timeout(self):
        import subprocess
        from shiptally.git_stats import _github_metadata
        result = subprocess.CompletedProcess([], 0, '{"private":false,"stargazers_count":7}')
        with patch("shiptally.git_stats.shutil.which", return_value="gh"), patch("shiptally.git_stats.subprocess.run", return_value=result) as run:
            self.assertEqual(_github_metadata("example/demo"), {"public": True, "stars": 7})
            self.assertEqual(run.call_args.args[0], ["gh", "api", "repos/example/demo"])
            self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_public_rest_fallback_has_ten_second_timeout(self):
        import io
        from shiptally.git_stats import _github_metadata
        response = io.BytesIO(b'{"private":false,"stargazers_count":8}')
        with patch("shiptally.git_stats.shutil.which", return_value=None), patch("shiptally.git_stats.urllib.request.urlopen", return_value=response) as call:
            self.assertEqual(_github_metadata("example/demo"), {"public": True, "stars": 8})
            self.assertEqual(call.call_args.args[0].full_url, "https://api.github.com/repos/example/demo")
            self.assertEqual(call.call_args.kwargs["timeout"], 10)

    def test_malformed_metadata_is_unknown(self):
        import subprocess
        from shiptally.git_stats import _github_metadata
        with patch("shiptally.git_stats.shutil.which", return_value="gh"), patch("shiptally.git_stats.subprocess.run", return_value=subprocess.CompletedProcess([], 0, '[]')):
            self.assertIsNone(_github_metadata("example/demo"))
