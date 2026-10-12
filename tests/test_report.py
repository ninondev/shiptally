# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shiptally.parse_claude import parse_lines as claude
from shiptally.parse_codex import parse_lines as codex
from shiptally.projects import Mapper, redact
from shiptally.report import build
from .test_parsers import assistant, lines, token_record


class ReportTests(unittest.TestCase):
    def test_global_claude_dedupe_fullest_then_oldest_file(self):
        a, b = claude(lines(assistant(output=3))), claude(lines(assistant(output=10)))
        a.update(birth=1, sid="old")
        b.update(birth=2, sid="new")
        result = build([a, b], Mapper())
        self.assertEqual(result["summary"]["claude_output_tokens"], 10)
        self.assertEqual(result["summary"]["sessions"], 1)
        self.assertAlmostEqual(result["summary"]["list_price_usd"], .0006)
        tie = assistant(output=10)
        tie["cwd"] = "/example/other"
        a = claude(lines(tie))
        a.update(birth=1, sid="earlier")
        result = build([b, a], Mapper())
        self.assertEqual(result["projects"][0]["name"], "other")

    def test_codex_fork_resume_global_response_dedupe(self):
        record = {"type": "token_usage_record", "timestamp": "2026-01-01T12:00:00Z",
                  "payload": {"response_id": "rid", "usage": {"output_tokens": 25}}}
        a, b = codex(lines(record), "original"), codex(lines(record), "fork")
        result = build([a, b], Mapper())
        self.assertEqual(result["summary"]["codex_output_tokens"], 25)
        self.assertEqual(result["summary"]["list_price_usd"], 0)
        self.assertEqual(result["summary"]["sessions"], 1)

    def test_fallback_cross_file_limitation_matches_v0(self):
        record = token_record((100, 20, 30, 0, 130), (10, 2, 3, 0, 13))
        result = build([codex(lines(record), "same"), codex(lines(record), "same")], Mapper())
        self.assertEqual(result["summary"]["codex_output_tokens"], 6)
        self.assertEqual(result["summary"]["sessions"], 1)

    def test_date_filter_and_utc_day(self):
        a = assistant()
        a["timestamp"] = "2026-01-01T23:30:00-02:00"
        result = build([claude(lines(a))], Mapper(), "2026-01-02", "2026-01-02")
        self.assertEqual(result["summary"]["active_days"], 1)
        self.assertEqual(result["daily"][0]["day"], "2026-01-02")
        self.assertEqual(build([claude(lines(a))], Mapper(), until="2026-01-01")["projects"], [])

    def test_hide_excludes_totals_and_merge_keeps_all_paths(self):
        a, b = assistant("a"), assistant("b")
        b["cwd"] = "/example/second"
        b["sessionId"] = "second"
        entries = [claude(lines(a)), claude(lines(b))]
        rules = [{"match": ["project", "second"], "merge": "group", "name": "Shared"}]
        result = build(entries, Mapper(rules))
        self.assertEqual(len(result["projects"]), 1)
        self.assertEqual(result["projects"][0]["sessions"], 2)
        self.assertEqual(len(result["projects"][0]["paths"]), 2)
        result = build(entries, Mapper([{"match": ["second"], "hide": True}]))
        self.assertEqual(result["summary"]["claude_output_tokens"], 10)

    def test_redaction_all_formats_have_no_source_identity(self):
        report = build([claude(lines(assistant()))], Mapper())
        sanitized = redact(report)
        text = json.dumps(sanitized)
        self.assertNotIn("/example", text)
        self.assertNotEqual(sanitized["projects"][0]["name"], "project")
        self.assertEqual(redact(report), sanitized)


class CLITests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[2] / "_jobs" / "shiptally3" / "tmp"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
        self.log = self.root / "fixture.jsonl"
        self.log.write_text("".join(lines(assistant())), encoding="utf-8")
        self.config = self.root / "config.toml"
        self.config.write_text("", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        from shiptally.cli import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--no-default-sources", "--source", str(self.log), "--config", str(self.config), "--no-cache", *args])
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_json_schema_and_actual_summary(self):
        result = json.loads(self.run_cli("--json"))
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(set(result), {"schema_version", "basis", "pricing", "window", "summary", "projects", "daily", "monthly", "warnings", "diagnostics"})
        self.assertEqual(result["summary"]["claude_output_tokens"], 10)
        self.assertEqual(result["diagnostics"]["parsed"], 1)
        self.assertIn("not a bill", result["basis"])
        self.assertIn("Spent $0.00 (list price) over 1 days -> 0 commits in 0 repos, run with --github to count public repos and stars", self.run_cli())

    def test_home_name_and_paths_are_shortened_in_every_output(self):
        home = self.root / "synthetic-user"
        home.mkdir()
        record = assistant()
        record["cwd"] = str(home)
        self.log.write_text("".join(lines(record)), encoding="utf-8")
        with patch("shiptally.projects.Path.home", return_value=home):
            data = json.loads(self.run_cli("--json"))
            text = self.run_cli("--verbose")
            html_path = self.root / "home.html"
            self.run_cli("--html", str(html_path))
            redacted = json.loads(self.run_cli("--redact", "--json"))
        self.assertEqual(data["projects"][0]["name"], "~ (home folder)")
        self.assertEqual(data["projects"][0]["paths"], ["~"])
        self.assertEqual(redacted["projects"][0]["name"], "~ (home folder)")
        for output in (json.dumps(data), text, html_path.read_text()):
            self.assertIn("~ (home folder)", output)
            self.assertNotIn("synthetic-user", output)

    def test_cli_author_modes_reach_rows_and_summary(self):
        for flags, expected in (([], "Exact author email"), (["--all-authors"], "All authors"),
                                (["--author", "Example"], "Git --author pattern: Example")):
            data = json.loads(self.run_cli("--json", *flags))
            self.assertIn(expected, data["summary"]["author_rule"])
            self.assertIn(expected, data["projects"][0]["author_rule"])
            self.assertIn(expected, self.run_cli(*flags))

    def test_demo_bypasses_all_local_inputs_and_is_deterministic(self):
        from shiptally.cli import main
        output = self.root / "demo.html"
        captures = []
        with patch("shiptally.cli.read_report", side_effect=AssertionError("local input read")), \
             patch("shiptally.git_stats._run", side_effect=AssertionError("git read")):
            for _ in range(2):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["--demo", "--json"]), 0)
                captures.append(out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--demo", "--html", str(output)]), 0)
        self.assertEqual(captures[0], captures[1])
        data = json.loads(captures[0])
        self.assertTrue(data["demo"])
        self.assertEqual(data["summary"]["list_price_usd"], 428.7664123)
        self.assertEqual(data["summary"]["repo_count"], 7)
        self.assertEqual(data["summary"]["active_days"], 60)
        self.assertEqual(data["demo_label"], "Synthetic demo data")
        self.assertEqual(data["diagnostics"]["files"], 0)
        self.assertIn("Synthetic demo data", output.read_text())

    def test_demo_rejects_input_and_network_options_and_author_modes_conflict(self):
        from shiptally.cli import main
        for flags in (["--demo", "--github"], ["--demo", "--source", "missing"],
                      ["--demo", "--since", "2026-09-01"], ["--all-authors", "--author", "x"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(flags)
            self.assertEqual(error.exception.code, 2)

    def test_html_written_and_json_redacted(self):
        output = self.root / "report.html"
        self.run_cli("--html", str(output), "--lang", "zh", "--redact")
        html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="zh-CN">', html)
        self.assertNotIn("/example", html)
        data = json.loads(self.run_cli("--json", "--redact"))
        self.assertNotIn("/example", json.dumps(data))

    def test_supplied_codex_prices_and_validation(self):
        from shiptally.cli import read_prices
        price = self.root / "prices.json"
        price.write_text('{"input": 2, "cached_input": 0.5, "output": 8}')
        self.assertEqual(read_prices(price)["output"], 8)
        for bad in ('{"input": -1, "cached_input": 0, "output": 8}', '{"input": 1, "cached_input": 0, "output": NaN}', '{}'):
            price.write_text(bad)
            with self.assertRaises(ValueError):
                read_prices(price)

    def test_explicit_bad_sources_fail_without_claiming_zero(self):
        from shiptally.cli import main
        for path in (self.root / "missing", self.config):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["--no-default-sources", "--source", str(path), "--config", str(self.config), "--no-cache"])
            self.assertEqual(code, 1)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("shiptally:", err.getvalue())

    def test_json_project_metrics_are_present(self):
        result = json.loads(self.run_cli("--json"))
        project = result["projects"][0]
        expected = {"name", "key", "paths", "list_price_usd", "claude_output_tokens", "codex_output_tokens",
                    "sessions", "active_days", "first_activity", "last_activity", "commits", "lines_added",
                    "lines_removed", "github_remote", "public", "stars"}
        self.assertTrue(expected.issubset(project))
        self.assertIsNone(project["codex_list_price_usd"])

    def test_extra_sources_add_to_environment_roots_and_can_be_isolated(self):
        from shiptally.cli import main
        folder = self.root / "claude" / "projects"
        folder.mkdir(parents=True)
        (folder / "default.jsonl").write_text("".join(lines(assistant("default", 20))))
        env = {"CLAUDE_CONFIG_DIR": str(folder.parent), "CODEX_HOME": str(self.root / "empty-codex")}
        for flags, expected in (([], 30), (["--no-default-sources"], 10)):
            out = io.StringIO()
            with patch.dict(os.environ, env), contextlib.redirect_stdout(out):
                code = main(["--source", str(self.log), "--config", str(self.config), "--no-cache", "--json", *flags])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["summary"]["claude_output_tokens"], expected)

    def test_github_summary_reuses_metadata_and_has_no_false_unknowns(self):
        import subprocess
        from shiptally.cli import main
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/example/demo"], check=True)
        record = assistant()
        record["cwd"] = str(repo)
        self.log.write_text("".join(lines(record)))
        out = io.StringIO()
        with patch("shiptally.git_stats._github_metadata", return_value={"public": True, "stars": 7}) as fetch, contextlib.redirect_stdout(out):
            code = main(["--no-default-sources", "--source", str(self.log), "--config", str(self.config), "--no-cache", "--github", "--json"])
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["summary"]["public"], 1)
        self.assertEqual(result["summary"]["stars"], 7)
        self.assertEqual(result["summary"]["github_unknown_repos"], [])
        fetch.assert_called_once_with("example/demo")
