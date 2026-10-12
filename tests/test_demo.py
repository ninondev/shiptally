# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
import contextlib
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build_backend
from shiptally.demo import DAYS, LABEL, SEED, sample
from shiptally.render_html import render
from shiptally.render_text import render as render_text


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT.parent / "_jobs" / "shiptally3" / "tmp"


class DemoTests(unittest.TestCase):
    def test_seven_project_types_cover_sixty_consecutive_days(self):
        data = sample()
        self.assertEqual(len(data["projects"]), 7)
        self.assertEqual({p["demo_kind"] for p in data["projects"]},
                         {"menu-bar app", "CLI", "web dashboard", "game mod",
                          "abandoned experiment", "library", "research notebook"})
        self.assertEqual(data["window"], {"since": "2026-08-01", "until": "2026-09-29", "timezone": "UTC"})
        self.assertEqual(data["summary"]["active_days"], DAYS)
        start = date.fromisoformat(data["window"]["since"])
        self.assertEqual([b["day"] for b in data["daily"]],
                         [(start + timedelta(days=i)).isoformat() for i in range(60)])
        self.assertEqual([b["month"] for b in data["monthly"]], ["2026-08", "2026-09"])
        for project in data["projects"]:
            self.assertGreaterEqual(project["sessions"], project["active_days"])
            self.assertGreater(project["claude_output_tokens"], 0)
            self.assertGreater(project["codex_output_tokens"], 0)

    def test_heavy_user_volume_and_contrasting_output(self):
        data = sample()
        self.assertGreater(data["summary"]["list_price_usd"], 200)
        self.assertTrue(400 <= data["summary"]["sessions"] <= 1200)
        for field in ("claude_output_tokens", "codex_output_tokens"):
            self.assertTrue(3_000_000 <= data["summary"][field] <= 30_000_000)
        projects = {p["demo_kind"]: p for p in data["projects"]}
        abandoned = projects["abandoned experiment"]
        self.assertGreater(abandoned["list_price_usd"], 20)
        self.assertEqual((abandoned["commits"], abandoned["lines_added"], abandoned["lines_removed"]), (0, 0, 0))
        self.assertLess(abandoned["last_activity"], "2026-09-01")
        library = projects["library"]
        self.assertGreaterEqual(library["commits"], 100)
        self.assertLess(library["list_price_usd"], 5)
        self.assertLess(library["claude_output_tokens"] + library["codex_output_tokens"], 100_000)
        self.assertEqual(data["summary"]["repo_count"], 7)
        self.assertEqual(data["summary"]["commits"], 402)
        self.assertIn("Precomputed fictional", data["demo_git_method"])

    def test_project_daily_monthly_and_summary_totals_agree(self):
        data = sample()
        for field in ("list_price_usd", "claude_output_tokens", "codex_output_tokens"):
            for group in ("projects", "daily", "monthly"):
                self.assertAlmostEqual(sum(p[field] for p in data[group]), data["summary"][field], places=7)
            for month in data["monthly"]:
                self.assertAlmostEqual(month[field], sum(d[field] for d in data["daily"]
                                                        if d["day"].startswith(month["month"])), places=7)
        for field in ("sessions", "commits", "lines_added", "lines_removed", "repo_count"):
            self.assertEqual(sum(p[field] for p in data["projects"]), data["summary"][field])
        self.assertEqual(data["summary"]["first_activity"], data["window"]["since"])
        self.assertEqual(data["summary"]["last_activity"], data["window"]["until"])

    def test_fixed_seed_does_not_use_or_change_global_random_state(self):
        state = random.getstate()
        try:
            first = sample()
            self.assertEqual(random.getstate(), state)
            random.seed(999)
            self.assertEqual(first, sample())
            self.assertEqual(first["demo_seed"], SEED)
            first["projects"][0]["paths"].append("changed")
            self.assertNotIn("changed", sample()["projects"][0]["paths"])
        finally:
            random.setstate(state)

    def test_every_demo_output_retains_explicit_label_without_inputs_or_network(self):
        from shiptally.cli import main
        TMP.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(TMP)) as directory, \
             patch("shiptally.cli.read_report", side_effect=AssertionError("local inputs")), \
             patch("shiptally.git_stats._run", side_effect=AssertionError("git scan")), \
             patch("shiptally.projects._git", side_effect=AssertionError("git resolution")), \
             patch("shiptally.git_stats.urllib.request.urlopen", side_effect=AssertionError("network")):
            for lang in ("en", "zh"):
                for redacted in (False, True):
                    flags = ["--demo", "--lang", lang] + (["--redact"] if redacted else [])
                    html = Path(directory) / (lang + str(redacted) + ".html")
                    for output in ([], ["--verbose"], ["--json"], ["--html", str(html)]):
                        with self.subTest(lang=lang, redacted=redacted, output=output):
                            capture = io.StringIO()
                            with contextlib.redirect_stdout(capture):
                                self.assertEqual(main(flags + output), 0)
                            self.assertIn(LABEL, capture.getvalue())
                            if "--json" in output:
                                self.assertEqual(json.loads(capture.getvalue())["demo_label"], LABEL)
                            if "--html" in output:
                                self.assertIn(LABEL, html.read_text(encoding="utf-8"))

    def test_render_script_handles_relative_path_with_spaces_outside_repository(self):
        TMP.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(TMP)) as directory:
            result = subprocess.run([str(ROOT / "scripts" / "render-demo.sh"), "demo with spaces.html"],
                                    cwd=directory, env=dict(os.environ, PYTHON=sys.executable),
                                    capture_output=True, text=True, check=True)
            output = Path(directory) / "demo with spaces.html"
            self.assertEqual(output.read_text(encoding="utf-8"), render(sample()))
            self.assertIn(LABEL, result.stdout)
            for args in ([], ["one", "two"]):
                invalid = subprocess.run([str(ROOT / "scripts" / "render-demo.sh"), *args],
                                         cwd=directory, capture_output=True, text=True)
                self.assertEqual(invalid.returncode, 2)
                self.assertIn("Usage:", invalid.stderr)

    def test_packaged_wheel_runs_demo_outside_source_tree(self):
        TMP.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(TMP)) as directory:
            wheel = Path(directory) / build_backend.build_wheel(directory)
            code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                    "from shiptally.cli import main; sys.exit(main(['--demo', '--json']))")
            result = subprocess.run([sys.executable, "-I", "-c", code, str(wheel)],
                                    cwd=directory, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), sample())

    def test_bundled_html_and_readme_output_are_reproducible(self):
        self.assertEqual((ROOT / "docs" / "demo.html").read_text(encoding="utf-8"), render(sample()))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        example = readme.split("```text\n", 1)[1].split("```", 1)[0]
        self.assertEqual(example, render_text(sample()))
