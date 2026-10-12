# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
import unittest
from pathlib import Path
from unittest.mock import patch
from html.parser import HTMLParser

from shiptally import render_html, render_text


def fixture():
    project = {"name": "synthetic-book", "paths": ["/synthetic/book"], "list_price_usd": 12.5,
               "claude_output_tokens": 1200, "codex_output_tokens": 400,
               "sessions": 3, "active_days": 2, "first_activity": "2026-01-01",
               "last_activity": "2026-01-02", "commits": 4, "lines_added": 80,
               "lines_removed": 7, "github_remote": True, "public": None, "stars": None}
    return {"schema_version": 1, "summary": {**project, "repo_count": 1},
            "projects": [project], "pricing": {"codex": "tokens only"}, "warnings": [],
            "window": {"since": "2026-01-01", "until": "2026-01-02", "timezone": "UTC"},
            "monthly": [{"month": "2026-01", "list_price_usd": 12.5,
                         "claude_output_tokens": 1200, "codex_output_tokens": 400}],
            "daily": [{"day": "2026-01-01", "list_price_usd": 10.0,
                       "claude_output_tokens": 1000, "codex_output_tokens": 0},
                      {"day": "2026-01-02", "list_price_usd": 2.5,
                       "claude_output_tokens": 200, "codex_output_tokens": 400}]}


class TextTests(unittest.TestCase):
    def test_project_labels_omit_repeated_names_but_keep_custom_names(self):
        cases = [("alpha", "~/Projects/alpha", "~/Projects/alpha"),
                 ("alpha", "~/Projects/alpha/", "~/Projects/alpha/"),
                 ("alpha", "~/Projects/alphabeta", "~/Projects/alphabeta · alpha"),
                 ("Alpha", "~/Projects/alpha", "~/Projects/alpha · Alpha"),
                 ("Friendly name", "~/Projects/alpha", "~/Projects/alpha · Friendly name"),
                 ("alpha", "", "alpha"),
                 ("~ (home folder)", "~", "~ (home folder)")]
        for lang in ("en", "zh"):
            for name, root, expected in cases:
                with self.subTest(lang=lang, name=name, root=root):
                    report = fixture()
                    project = report["projects"][0]
                    project.update(name=name, repo_paths=[root] if root else [], paths=[root] if root else [])
                    self.assertEqual(render_text.project_identity(project, lang)[0], expected)
                    row = render_text.render(report, lang).splitlines()[4]
                    self.assertEqual(row.split("  ", 1)[0], expected)
                    html = render_html.render(report, lang)
                    document = Document(html)
                    titles = [attrs["title"] for tag, attrs in document.tags
                              if attrs.get("class") == "project-line"]
                    self.assertEqual(titles, [expected])
                    self.assertNotIn("~ · ~ (home folder)", html)

    def test_duplicate_name_uses_repo_root_and_preserves_folder_disclosure(self):
        report = fixture()
        project = report["projects"][0]
        project.update(name="alpha", repo_paths=["~/Projects/alpha"],
                       paths=["~/Projects/alpha/src", "~/Projects/alpha/tests"])
        text = render_text.render(report)
        self.assertIn("~/Projects/alpha (2 folders)", text)
        self.assertNotIn(" · alpha", text)
        html = render_html.render(report)
        self.assertNotIn(" · alpha", html)
        self.assertIn("<details><summary>", html)
        self.assertIn("2 folders", html)
        for path in project["paths"]:
            self.assertIn(path, html)
        self.assertIn("~/Projects/alpha/src", render_text.render(report, verbose=True))

    def test_summary_explains_how_to_check_github(self):
        self.assertEqual(render_text.summary_line(fixture()),
                         "Spent $12.50 (list price) over 2 days -> 4 commits in 1 repos, run with --github to count public repos and stars")
        report = fixture()
        report["summary"]["github_checked"] = True
        self.assertIn("unknown public, unknown stars", render_text.summary_line(report))

    def test_table_has_metrics_and_price_note(self):
        output = render_text.render(fixture())
        for text in ("synthetic-book", "1,200", "400", "2026-01-01", "2026-01-02", "Commits",
                     "Lines +/-", "+80/-7", "Public ★", "First–last", "not a bill", "tokens only"):
            self.assertIn(text, output)

    def test_folders_only_listed_in_verbose_text(self):
        report = fixture()
        project = report["projects"][0]
        project["repo_paths"] = ["~/Projects/book"]
        project["paths"] = ["~/Projects/book/folder-%03d" % i for i in range(300)]
        output = render_text.render(report)
        self.assertIn("~/Projects/book", output)
        self.assertIn("300 folders", output)
        self.assertNotIn("folder-000", output)
        verbose = render_text.render(report, verbose=True)
        for path in project["paths"]:
            self.assertIn(path, verbose)

    def test_terminal_fits_160_columns_with_long_and_wide_names(self):
        report = fixture()
        report["projects"][0]["name"] = "長" * 300
        report["projects"][0]["claude_output_tokens"] = 10 ** 200
        report["projects"][0]["paths"] = ["/example/" + "x" * 500]
        output = render_text.render(report, verbose=True)
        self.assertIn("…", output)
        self.assertTrue(all(render_text._width(line) <= 160 for line in output.splitlines()))

    def test_long_names_keep_repository_root_in_compact_row(self):
        report = fixture()
        project = report["projects"][0]
        project["name"] = "long-project-" * 40
        project["repo_paths"] = ["~/Projects/book"]
        project["paths"] = ["~/Projects/book/a", "~/Projects/book/b"]
        self.assertIn("~/Projects/book", render_text.render(report))
        html = render_html.render(report)
        line = html[html.index('<span class="project-line"'):html.index('</summary>')]
        self.assertLess(line.index('class="location"'), line.index(project["name"] + '</span>'))

    def test_home_prefix_shortens_paths_keys_and_diagnostics_without_prefix_collision(self):
        from shiptally.projects import display_report
        report = fixture()
        report["projects"][0]["paths"] = ["/synthetic/person/book"]
        report["projects"][0]["key"] = "git:/synthetic/person/book/.git"
        report["warnings"] = ["Cannot read /synthetic/person/book", "Cannot read /synthetic/person."]
        report["diagnostics"] = {"/synthetic/person/file": "/synthetic/person-other/file"}
        with patch("shiptally.projects.Path.home", return_value=Path("/synthetic/person")):
            shown = display_report(report)
            for output in (render_text.render(report, verbose=True), render_html.render(report)):
                self.assertNotIn("/synthetic/person/book", output)
                self.assertIn("~/book", output)
        self.assertEqual(shown["projects"][0]["key"], "git:~/book/.git")
        self.assertEqual(shown["diagnostics"], {"~/file": "/synthetic/person-other/file"})
        self.assertEqual(shown["warnings"][1], "Cannot read ~.")
        self.assertEqual(report["projects"][0]["paths"], ["/synthetic/person/book"])

    def test_sort_and_terminal_control_safety(self):
        report = fixture()
        report["projects"].append({**report["projects"][0], "name": "low\x1b[31m", "list_price_usd": 1})
        output = render_text.render(report)
        self.assertLess(output.index("synthetic-book"), output.index("low"))
        self.assertNotIn("\x1b", output)

    def test_chinese_and_empty(self):
        report = fixture()
        self.assertIn("标价等值", render_text.render(report, "zh"))
        report["projects"] = []
        self.assertIn("No activity", render_text.render(report))


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class HtmlTests(unittest.TestCase):
    def test_hundreds_of_folders_are_in_closed_details_with_one_line_summary(self):
        report = fixture()
        project = report["projects"][0]
        project["repo_paths"] = ["~/Projects/book"]
        project["paths"] = ["~/Projects/book/folder-%03d" % i for i in range(300)]
        output = render_html.render(report)
        document = Document(output)
        details = [attrs for tag, attrs in document.tags if tag == "details"]
        self.assertEqual(details, [{}])
        start, end = output.index('<details>'), output.index('</details>')
        summary = output[start:output.index('</summary>')]
        self.assertIn("~/Projects/book", summary)
        self.assertIn("300 folders", summary)
        self.assertNotIn('<br>', summary)
        for path in project["paths"]:
            self.assertIn(path, output[start:end])
            self.assertNotIn(path, output[:start] + output[end:])

    def test_compact_columns_have_fixed_widths_and_inline_dates(self):
        output = render_html.render(fixture())
        document = Document(output)
        cols = [attrs for tag, attrs in document.tags if tag == "col"]
        self.assertEqual(len(cols), 10)
        self.assertEqual(sum(int(attrs["style"][6:-1]) for attrs in cols), 100)
        self.assertIn("table-layout:fixed", output)
        self.assertNotIn("min-width:1160px", output)
        self.assertIn('<td class="dates" title="2026-01-01–2026-01-02">01-01 – 01-02</td>', output)
        for value in ("Lines +/-", "Public ★", "First–last"):
            self.assertIn(value, output)
        self.assertNotIn("unknown / unknown", output)
        self.assertIn("needs --github", output)

    def test_answer_line_sits_under_the_subtitle_with_an_arrow(self):
        for lang, expected in (("en", "$12.50 list price over 2 days → 4 commits in 1 repositories."),
                               ("zh", "2 天投入标价 $12.50 → 1 个仓库 4 次提交。")):
            with self.subTest(lang=lang):
                html = render_html.render(fixture(), lang)
                sub = html.index('class="sub"')
                answer = html.index('class="answer"')
                self.assertLess(sub, answer)
                self.assertIn('<p class="answer">' + expected + "</p>", html)
                self.assertNotIn("->", html[answer:answer + 200])
                self.assertNotIn("--github", html[answer:answer + 200])
        self.assertNotIn('class="note summary"', render_html.render(fixture()))

    def test_spend_without_commits_gets_a_muted_tag(self):
        report = fixture()
        report["projects"][0].update(commits=0, lines_added=0, lines_removed=0)
        for lang, tag in (("en", "no commits"), ("zh", "无提交")):
            with self.subTest(lang=lang):
                html = render_html.render(report, lang)
                self.assertIn('<span class="no-commits">' + tag + "</span>", html)
        report["projects"][0]["list_price_usd"] = 0
        self.assertNotIn("no commits", render_html.render(report))
        report["projects"][0].update(list_price_usd=12.5, commits=4)
        self.assertNotIn("no commits", render_html.render(report))

    def test_cross_year_dates_keep_full_form(self):
        report = fixture()
        report["projects"][0]["first_activity"] = "2025-12-30"
        self.assertIn('<td class="dates">2025-12-30–2026-01-02</td>', render_html.render(report))

    def test_daily_plot_marks_month_starts_once(self):
        report = fixture()
        report["daily"] = [{"day": f"2026-08-{d:02d}", "list_price_usd": 1.0,
                            "claude_output_tokens": 1, "codex_output_tokens": 0} for d in range(1, 4)]
        report["daily"] += [{"day": "2026-09-01", "list_price_usd": 2.0, "claude_output_tokens": 1, "codex_output_tokens": 0},
                            {"day": "2026-09-02", "list_price_usd": 0.5, "claude_output_tokens": 1, "codex_output_tokens": 0}]
        html = render_html.render(report)
        self.assertIn('<div class="months"><span style="left:70.00%">09-01</span></div>', html)
        self.assertEqual(html.count("09-01</span>"), 1)

    def test_author_rule_is_visible_in_html_summary(self):
        report = fixture()
        report["summary"]["author_rule"] = "All authors (--all-authors)"
        self.assertIn("Commit authors: All authors (--all-authors)", render_html.render(report))

    def test_large_money_cells_use_bounded_display_with_full_value_title(self):
        report = fixture()
        report["projects"][0]["list_price_usd"] = 123456789012.34
        html = render_html.render(report)
        self.assertIn('<td class="num money-edge red"><span class="cell" title="123,456,789,012.34">', html)

    def test_offline_structure_and_accessible_values(self):
        output = render_html.render(fixture())
        document = Document(output)
        ids = {attrs.get("id") for _, attrs in document.tags}
        self.assertTrue({"summary-title", "projects-title", "monthly", "daily", "theme"}.issubset(ids))
        self.assertEqual(sum(tag == "table" for tag, _ in document.tags), 3)
        self.assertEqual(sum(tag == "caption" for tag, _ in document.tags), 1)
        self.assertTrue(any(attrs.get("class") == "t-account" for _, attrs in document.tags))
        self.assertTrue(any("money-edge" in attrs.get("class", "") for _, attrs in document.tags))
        for tag, attrs in document.tags:
            self.assertNotIn("src", attrs)
            self.assertNotIn("href", attrs)
            if tag == "th":
                self.assertIn(attrs.get("scope"), ("col", "row"))
        self.assertNotIn("http://", output)
        self.assertNotIn("https://", output)
        for value in ("2026-01-01", "2026-01-02", "12.50", "1,200", "400", "unknown", "not a bill"):
            self.assertIn(value, output)
        self.assertIn("button.addEventListener('click'", output)
        self.assertIn("prefers-color-scheme", output)

    def test_project_path_and_warning_are_escaped(self):
        report = fixture()
        payload = '</th><script src="evil">x</script>'
        report["projects"][0]["name"] = payload
        report["projects"][0]["paths"] = [payload]
        report["warnings"] = [payload]
        output = render_html.render(report)
        self.assertNotIn(payload, output)
        self.assertIn("&lt;script src=&quot;evil&quot;&gt;", output)
        scripts = [attrs for tag, attrs in Document(output).tags if tag == "script"]
        self.assertEqual(scripts, [{}])

    def test_chinese_and_empty_charts(self):
        report = fixture()
        output = render_html.render(report, "zh")
        self.assertIn('lang="zh-CN"', output)
        for value in ("投入", "产出", "每月投入与输出", "每日投入与输出", "标价等值"):
            self.assertIn(value, output)
        report["projects"] = []
        report["daily"] = []
        report["monthly"] = []
        self.assertIn("No activity in this window", render_html.render(report))


if __name__ == "__main__":
    unittest.main()
