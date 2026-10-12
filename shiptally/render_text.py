# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
"""Plain terminal ledger and a short summary of spend and output."""
import unicodedata
from .projects import display_report


def _number(value):
    return "?" if value is None else format(value, ",")


def _label(value, lang):
    return ("未知" if lang == "zh" else "unknown") if value is None else str(value)


def _safe(value):
    # Project names come from local paths or user config; strip terminal controls.
    return "".join(c if c.isprintable() else " " for c in str(value))


def _width(value):
    return sum(0 if unicodedata.combining(c) else
               2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in str(value))


def _truncate(value, limit):
    value = _safe(value)
    if _width(value) <= limit:
        return value
    result = ""
    for char in value:
        if _width(result + char) > limit - 1:
            break
        result += char
    return result + "…"


def project_location(project, lang="en"):
    roots = project.get("repo_paths") or project.get("paths") or []
    root = roots[0] if roots else ""
    count = len(set(project.get("paths", [])))
    folders = (f"{count} 个目录" if lang == "zh" else f"{count} folders") if count > 1 else ""
    return root, folders


def project_identity(project, lang="en"):
    """Keep custom names, omit redundant basenames, and give home a single label."""
    name = project["name"]
    if name == "~ (home folder)":
        return name, "", ""
    root, folders = project_location(project, lang)
    if root and name == root.rstrip("/").rsplit("/", 1)[-1]:
        return root, root, folders
    prefix = root + " · " if root else ""
    return prefix + name, prefix, folders


def _wrap(value, limit=160):
    lines = []
    while _width(value) > limit:
        index = 0
        while index < len(value) and _width(value[:index + 1]) <= limit:
            index += 1
        split = value.rfind(" ", 0, index + 1)
        if split <= 0:
            split = index
        lines.append(value[:split])
        value = value[split:].lstrip()
    return lines + [value]


def summary_line(report, lang="en"):
    summary = report["summary"]
    usd = summary.get("list_price_usd", 0)
    days = summary.get("active_days", 0)
    commits = _label(summary.get("commits", 0), lang)
    repos = summary.get("repo_count", 0)
    public = _label(summary.get("public"), lang)
    stars = _label(summary.get("stars"), lang)
    checked = summary.get("github_checked", False)
    if lang == "zh":
        return (f"投入 ${usd:,.2f}（标价等值），{days} 个活跃日 -> "
                f"{repos} 个仓库、{commits} 次提交，" +
                (f"公开仓库 {public}，星标 {stars}" if checked else
                 "运行时加 --github 可统计公开仓库和星标"))
    return (f"Spent ${usd:,.2f} (list price) over {days} days -> "
            f"{commits} commits in {repos} repos, " +
            (f"{public} public, {stars} stars" if checked else
             "run with --github to count public repos and stars"))


def render(report, lang="en", verbose=False):
    report = display_report(report)
    zh = lang == "zh"
    columns = ["项目", "标价 $", "Claude 输出", "Codex 输出", "会话", "天", "最早–最近",
               "提交", "行 +/-", "公开 ★"] if zh else [
        "Project", "List $", "Claude out", "Codex out", "Sessions", "Days", "First–last",
        "Commits", "Lines +/-", "Public ★"]
    rows = []
    identities = []
    for project in sorted(report["projects"], key=lambda p: (-p["list_price_usd"], p["name"])):
        boolean = lambda value: ("?" if value is None else
                                 ("是" if value else "否") if zh else ("yes" if value else "no"))
        label, _, folders = project_identity(project, lang)
        suffix = " (" + folders + ")" if folders else ""
        identities.append((label, suffix))
        rows.append([
            _safe(label + suffix), f"{project['list_price_usd']:,.2f}",
            _number(project["claude_output_tokens"]), _number(project["codex_output_tokens"]),
            _number(project["sessions"]), _number(project["active_days"]),
            (project.get("first_activity") or "-") + "–" + (project.get("last_activity") or "-"),
            _number(project.get("commits")), "+" + _number(project.get("lines_added")) +
            "/-" + _number(project.get("lines_removed")),
            boolean(project.get("public")) + " ★" + _number(project.get("stars")),
        ])
    widths = [max(_width(row[i]) for row in [columns] + rows) for i in range(len(columns))]
    widths[0] = min(widths[0], 48)
    while sum(widths) + 2 * (len(widths) - 1) > 160:
        candidates = [i for i, w in enumerate(widths) if w > _width(columns[i])]
        widest = max(candidates, key=lambda i: widths[i])
        widths[widest] -= 1
    for row, (label, suffix) in zip(rows, identities):
        row[0] = _truncate(label, max(1, widths[0] - _width(suffix))) + suffix
    def line(row):
        cells = []
        for i, cell in enumerate(row):
            cell = _truncate(cell, widths[i])
            padding = " " * (widths[i] - _width(cell))
            cells.append(str(cell) + padding if i == 0 else padding + str(cell))
        return "  ".join(cells)
    output = [summary_line(report, lang)]
    if report.get("demo"):
        output.append("Synthetic demo data. 合成示例数据。" if zh else "Synthetic demo data.")
    rule = report["summary"].get("author_rule")
    if rule:
        output.append(("提交作者规则：" if zh else "Commit authors: ") + _safe(rule))
    output.extend(["", line(columns), line(["-" * w for w in widths])])
    output.extend(line(row) for row in rows)
    if verbose:
        for project in report["projects"]:
            output.append("")
            output.append(_safe(project["name"]) + (" 的目录：" if zh else " folders:"))
            output.extend("  " + _safe(path) for path in project.get("paths", []))
    if not rows:
        output.append("此时间段没有记录。" if zh else "No activity in this window.")
    output.extend(["", "标价等值，不是账单；订阅费用不同。" if zh else
                   "List-price equivalent, not a bill. Subscriptions differ."])
    if report.get("pricing", {}).get("codex") == "user-supplied":
        output.append("Codex 使用你提供的价格。" if zh else "Codex uses your supplied prices.")
    else:
        output.append("Codex 只计 token；未提供价格。" if zh else "Codex: tokens only; no prices supplied.")
    output.append("? = 未查询或不可用。日期以 UTC 计。" if zh else
                  "? = not checked or unavailable. Dates use UTC.")
    output.extend(_safe(warning) for warning in report.get("warnings", []))
    return "\n".join(part for item in output for part in _wrap(item)) + "\n"
