# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
"""Render one offline account book, with no fetched fonts, scripts, or images."""
from html import escape

from .render_text import summary_line, project_identity
from .projects import display_report


CSS = """
:root { --paper:#f5f0e6; --sheet:#fbf8f2; --ink:#1e1a15; --muted:#554d42;
 --rule:#c9bca5; --red:#a52a1f; --token:#736957; color-scheme:light; }
@media (prefers-color-scheme:dark) { :root:not([data-theme=light]) {
 --paper:#191612; --sheet:#211d18; --ink:#ece4d5; --muted:#b6aa96;
 --rule:#4d4438; --red:#f0897a; --token:#b6aa96; color-scheme:dark; } }
:root[data-theme=dark] { --paper:#191612; --sheet:#211d18; --ink:#ece4d5;
 --muted:#b6aa96; --rule:#4d4438; --red:#f0897a; --token:#b6aa96; color-scheme:dark; }
* { box-sizing:border-box; } body { margin:0; background:var(--paper); color:var(--ink);
 font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif; }
::selection { background:var(--red); color:var(--paper); }
:focus-visible { outline:2px solid var(--red); outline-offset:4px; }
html { scrollbar-color:var(--muted) var(--paper); }
main { max-width:1280px; margin:auto; padding:40px 32px 64px; }
header { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap;
 gap:12px 24px; padding-bottom:18px; border-bottom:3px double var(--ink); }
h1,h2,h3 { font-family:"Songti SC",STSong,Georgia,serif; }
h1 { margin:0; font-size:44px; line-height:1.15; letter-spacing:.02em; }
h2 { font-size:26px; margin:0 0 16px; } h3 { font-size:20px; margin:0 0 8px; }
p { margin:0 0 10px; } .sub,.note { color:var(--muted); max-width:75ch; }
.answer { font-size:19px; margin:14px 0 0; max-width:75ch; }
.sub { margin-top:10px; } .note { font-size:13px; } .price-note { padding:12px 0;
 max-width:none; border-bottom:1px solid var(--rule); } .red { color:var(--red); }
button { font:inherit; border:1px solid var(--rule); background:var(--sheet); color:var(--ink);
 padding:9px 14px; cursor:pointer; min-height:44px; border-radius:2px; }
button:hover { border-color:var(--ink); } section { padding-top:40px; }
.t-account { display:grid; grid-template-columns:1fr 1fr; border-top:1px solid var(--ink);
 border-bottom:3px double var(--ink); }
.account-side { padding:16px 0; } .account-side:first-child { padding-right:32px;
 border-right:1px solid var(--red); } .account-side:last-child { padding-left:32px; }
dl { margin:0; } dl>div { display:flex; justify-content:space-between; align-items:baseline;
 gap:16px; padding:7px 0; border-top:1px solid var(--rule); }
dt { color:var(--muted); } dd { margin:0; text-align:right; font-variant-numeric:tabular-nums; }
.lead dd { font-size:30px; line-height:1.3; font-weight:600; }
.scroll { overflow-x:auto; } table { border-collapse:collapse; width:100%; font-size:14px; }
caption { text-align:left; color:var(--muted); font-size:13px; margin-bottom:10px; }
th,td { text-align:left; vertical-align:top; border-bottom:1px solid var(--rule); padding:10px 9px; }
thead th { font-weight:500; font-size:12px; border-bottom:1px solid var(--ink); color:var(--muted); }
tbody th { font-weight:600; } .num { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.projects { table-layout:fixed; border-bottom:3px double var(--ink); }
.projects th,.projects td { padding:10px 6px; }
.cell,.project-line { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.project-line { font-weight:600; }
.location { color:var(--muted); font-weight:400; }
.folders { font-size:12px; font-weight:400; }
details { font-weight:400; }
summary { cursor:pointer; color:var(--ink); }
.summary-line { display:inline-flex; align-items:baseline; width:calc(100% - 16px); gap:6px; vertical-align:top; }
.summary-line .project-line { min-width:0; flex:1; }
.summary-line .folders { flex:none; color:var(--muted); }
.folder-list { max-height:280px; overflow:auto; }
.projects details .path { max-width:none; }
.money-edge { border-right:1px solid var(--red); padding-right:15px; }
.path { display:block; font-size:12px; font-weight:400; line-height:1.4; color:var(--muted);
 overflow-wrap:anywhere; margin-top:4px; }
.dates { white-space:nowrap; font-size:12px; line-height:23px; font-variant-numeric:tabular-nums; }
.charts { display:grid; grid-template-columns:minmax(0,5fr) minmax(0,7fr); gap:36px 56px; align-items:start; }
.plot { margin:0 0 18px; } .plot .cols { display:flex; align-items:flex-end; gap:2px; height:120px;
 border-bottom:1px solid var(--ink); } .plot i { flex:1 1 0; min-height:1px; background:var(--red); opacity:.72; }
.plot i.top { opacity:1; } .plot .axis { display:flex; justify-content:space-between; gap:12px; font-size:12px;
 color:var(--muted); margin-top:4px; font-variant-numeric:tabular-nums; }
.months { position:relative; height:18px; font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; }
.months span { position:absolute; top:3px; transform:translateX(-50%); }
.months span::before { content:""; position:absolute; left:50%; top:-8px; height:6px; border-left:1px solid var(--muted); }
.no-commits { display:inline-block; margin-top:3px; padding:0 6px; border:1px solid var(--rule);
 border-radius:2px; font-size:11px; font-weight:400; color:var(--muted); }
dd.plain { color:var(--muted); }
.capped { max-height:26rem; overflow-y:auto; border-bottom:1px solid var(--ink); } .capped thead th { position:sticky; top:0; background:var(--paper); z-index:1; }
dd.hint { color:var(--muted); font-size:13px; }
.charts section { min-width:0; } .chart { min-width:380px; }
.chart td { min-width:90px; } .chart tbody th { font-weight:500; white-space:nowrap; } .bar { display:block; height:8px; background:var(--red);
 margin-top:7px; } .bar.token { background:var(--token); }
.chart-label { display:block; margin-top:5px; font-size:11px; color:var(--muted); }
.empty { padding:16px 0; color:var(--muted); } footer { margin-top:36px; padding-top:14px;
 border-top:1px solid var(--rule); } .summary { margin-top:18px; }
@media (max-width:1100px) { .projects { min-width:1040px; } .projects caption { max-width:calc(100vw - 40px); } }
@media (max-width:760px) { main { padding:24px 20px 40px; } h1 { font-size:36px; }
 .charts { grid-template-columns:1fr; gap:0; } .account-side:first-child { padding-right:16px; }
 .account-side:last-child { padding-left:16px; } dt { font-size:12px; } .lead dd { font-size:24px; }
 dl>div { flex-wrap:wrap; gap:0 12px; } section { padding-top:28px; } }
@media print { button { display:none; } main { max-width:none; padding:0; }
 .scroll { overflow:visible; } .projects { min-width:0; font-size:11px; }
 .projects th,.projects td { padding:5px 3px; } .path { font-size:11px; }
 .charts { grid-template-columns:1fr; } section { break-inside:avoid; } .capped { max-height:none; } }
"""


def _text(value):
    return escape(str(value), quote=True)


def render(report, lang="en"):
    report = display_report(report)
    zh = lang == "zh"
    def tr(en, cn):
        return cn if zh else en
    def number(value):
        return tr("unknown", "未知") if value is None else format(value, ",")
    def boolean(value):
        return tr("unknown", "未知") if value is None else tr("yes", "是") if value else tr("no", "否")
    def pair(label, value, lead=False):
        return '<div' + (' class="lead"' if lead else '') + '><dt>' + _text(label) + '</dt><dd>' + _text(value) + '</dd></div>'
    summary = report["summary"]
    inputs = [pair(tr("List-price equivalent", "标价等值"), f"${summary.get('list_price_usd', 0):,.2f}", True),
              pair(tr("Claude output tokens", "Claude 输出 token"), number(summary.get("claude_output_tokens", 0))),
              pair(tr("Codex output tokens", "Codex 输出 token"), number(summary.get("codex_output_tokens", 0))),
              pair(tr("Sessions / active days", "会话 / 活跃天数"), f"{summary.get('sessions', 0)} / {summary.get('active_days', 0)}")]
    outputs = [pair(tr("Commits", "提交"), number(summary.get("commits", 0)), True),
               pair(tr("Repositories", "仓库"), number(summary.get("repo_count", 0))),
               pair(tr("Lines added / removed", "新增行 / 删除行"), f"+{number(summary.get('lines_added', 0))} / -{number(summary.get('lines_removed', 0))}")]
    if summary.get("github_checked"):
        outputs.append(pair(tr("Public repositories / stars", "公开仓库 / 星标"),
                            f"{number(summary.get('public'))} / {number(summary.get('stars'))}"))
    else:
        outputs.append('<div><dt>' + _text(tr("Public repositories / stars", "公开仓库 / 星标")) + '</dt><dd class="plain">'
                       + _text(tr("needs --github", "需加 --github")) + '</dd></div>')
    labels = [tr("Project", "项目"), tr("List price $", "标价 $"), tr("Claude out", "Claude 输出"),
              tr("Codex out", "Codex 输出"), tr("Sessions", "会话"), tr("Days", "天"),
              tr("First–last", "最早–最近"), tr("Commits", "提交"),
              tr("Lines +/-", "行 +/-"), tr("Public ★", "公开 ★")]
    header = "".join('<th scope="col"' + (' class="num money-edge"' if i == 1 else ' class="num"' if i not in (0, 6) else '') + '><span class="cell" title="' + _text(label) + '">' + _text(label) + '</span></th>' for i, label in enumerate(labels))
    colgroup = '<colgroup>' + ''.join('<col style="width:' + str(width) + '%">' for width in
                                     (24, 8, 9, 9, 6, 4, 14, 6, 11, 9)) + '</colgroup>'
    window = report.get("window", {})
    def dates_cell(project):
        first = project.get("first_activity") or "-"
        last = project.get("last_activity") or "-"
        full = _text(first) + "–" + _text(last)
        year = (window.get("since") or "")[:4]
        if len(first) == 10 and len(last) == 10 and year and first[:4] == year and last[:4] == year:
            return '<td class="dates" title="' + full + '">' + _text(first[5:] + " – " + last[5:]) + '</td>'
        return '<td class="dates">' + full + '</td>'
    rows = []
    for project in sorted(report["projects"], key=lambda p: (-p["list_price_usd"], p["name"])):
        label, prefix, folders = project_identity(project, lang)
        identity = '<span class="project-line" title="' + _text(label) + '"><span class="location">' + _text(prefix) + '</span>' + _text(label[len(prefix):]) + '</span>'
        if folders:
            identity = '<details><summary><span class="summary-line">' + identity + '<span class="folders">' + _text(folders) + '</span></span></summary><div class="folder-list">' + ''.join(
                '<span class="path">' + _text(path) + '</span>' for path in project.get("paths", [])) + '</div></details>'
        money = f"{project['list_price_usd']:,.2f}"
        cells = ['<th scope="row">' + identity + '</th>',
                 '<td class="num money-edge red"><span class="cell" title="' + _text(money) + '">' + money + '</span></td>']
        for key in ("claude_output_tokens", "codex_output_tokens", "sessions", "active_days"):
            value = number(project.get(key, 0))
            cells.append('<td class="num"><span class="cell" title="' + _text(value) + '">' + _text(value) + '</span></td>')
        cells.append(dates_cell(project))
        commits_value = number(project.get("commits"))
        commits_cell = '<td class="num"><span class="cell" title="' + _text(commits_value) + '">' + _text(commits_value) + '</span>'
        if project.get("commits") == 0 and project.get("list_price_usd", 0) > 0:
            commits_cell += '<span class="no-commits">' + _text(tr("no commits", "无提交")) + '</span>'
        commits_cell += '</td>'
        cells.append(commits_cell)
        for value in ('+' + number(project.get("lines_added")) + '/-' + number(project.get("lines_removed")),
                      boolean(project.get("public")) + (' ★' + number(project.get("stars")) if project.get("public") else '')):
            cells.append('<td class="num"><span class="cell" title="' + _text(value) + '">' + _text(value) + '</span></td>')
        rows.append('<tr>' + "".join(cells) + '</tr>')
    if not rows:
        rows.append('<tr><td colspan="10" class="empty">' + tr("No activity in this window. Try a wider date range or another source.", "此时间段没有记录。可扩大日期范围，或换一个来源。") + '</td></tr>')

    def chart_table(kind):
        monthly = kind == "monthly"
        buckets = report.get(kind, [])
        fields = ("list_price_usd", "claude_output_tokens", "codex_output_tokens")
        maxima = [max((b.get(f, 0) for b in buckets), default=0) for f in fields]
        body = []
        for bucket in buckets:
            date = bucket["month" if monthly else "day"]
            cells = ['<th scope="row">' + _text(date) + '</th>']
            for index, field in enumerate(fields):
                value = bucket.get(field, 0)
                width = 100 * value / maxima[index] if maxima[index] else 0
                label = f"${value:,.2f}" if index == 0 else number(value)
                # Each quantity has its own scale; the exact numbers remain table text.
                cells.append('<td class="num">' + _text(label) + '<span aria-hidden="true" class="bar' + (' token' if index else '') + '" style="width:' + f"{width:.3f}%" + '"></span></td>')
            body.append('<tr>' + ''.join(cells) + '</tr>')
        if not body:
            body.append('<tr><td colspan="4" class="empty">' + tr("No activity in this window.", "此时间段没有记录。") + '</td></tr>')
        title = tr("Monthly spend and output", "每月投入与输出") if monthly else tr("Daily spend and output", "每日投入与输出")
        return ('<div class="scroll' + ('' if monthly else ' capped') + '" tabindex="0" role="region" aria-label="' + title + '"><table class="chart">'
                '<thead><tr><th scope="col">' + tr("Month" if monthly else "Day", "月份" if monthly else "日期") + '</th>'
                '<th scope="col" class="num">' + tr("List price $", "标价 $") + '</th><th scope="col" class="num">Claude ' + tr("out", "输出") + '</th>'
                '<th scope="col" class="num">Codex ' + tr("out", "输出") + '</th></tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>')

    def daily_plot():
        buckets = report.get("daily", [])
        maxima = max((b.get("list_price_usd", 0) for b in buckets), default=0)
        if len(buckets) < 2 or not maxima:
            return ''
        top = max(range(len(buckets)), key=lambda i: buckets[i].get("list_price_usd", 0))
        cols = ''.join('<i' + (' class="top"' if i == top else '') + ' style="height:' + f"{100 * b.get('list_price_usd', 0) / maxima:.1f}%" + '"></i>'
                       for i, b in enumerate(buckets))
        # a tick and label at each month start inside the window; the first and
        # last days already have their own labels on the axis
        marks = ''.join('<span style="left:' + f"{100 * (i + 0.5) / len(buckets):.2f}" + '%">' + _text(buckets[i]["day"][5:]) + '</span>'
                        for i, b in enumerate(buckets)
                        if b["day"].endswith("-01") and 0 < i < len(buckets) - 1)
        return ('<div class="plot" aria-hidden="true"><div class="cols">' + cols + '</div><div class="months">' + marks + '</div><div class="axis"><span>' + _text(buckets[0]["day"]) + '</span><span>'
                + tr("List price $ per day, peak ", "每日标价 $，最高 ") + _text(f"${maxima:,.2f}") + '</span><span>' + _text(buckets[-1]["day"]) + '</span></div></div>')

    price_note = tr("List-price equivalent, not a bill. Subscriptions differ.", "标价等值，不是账单；订阅费用不同。")
    codex_note = tr("Codex uses your supplied prices.", "Codex 使用你提供的价格。") if report.get("pricing", {}).get("codex") == "user-supplied" else tr("Codex: tokens only; no prices supplied.", "Codex 只计 token；未提供价格。")
    dates = _text(window.get("since") or "-") + " / " + _text(window.get("until") or "-") + " · UTC"
    warnings = "".join('<p class="note">' + _text(w) + '</p>' for w in report.get("warnings", []))
    author_note = '<p class="note">' + _text(tr("Commit authors: ", "提交作者规则：") + summary.get("author_rule", "")) + '</p>' if summary.get("author_rule") else ''
    demo_note = '<p class="note">' + tr("Synthetic demo data.", "Synthetic demo data. 合成示例数据。") + '</p>' if report.get("demo") else ''
    script = """const root=document.documentElement;const button=document.getElementById('theme');
const media=window.matchMedia('(prefers-color-scheme: dark)');
let dark=media.matches;let chosen=false;
function update(){root.dataset.theme=dark?'dark':'light';button.setAttribute('aria-pressed',String(dark));
button.textContent=dark?LIGHT:DARK;}
button.addEventListener('click',()=>{chosen=true;dark=!dark;update();});
if(media.addEventListener){media.addEventListener('change',e=>{if(!chosen){dark=e.matches;update();}});}
update();""".replace("LIGHT", "'浅色模式'" if zh else "'Light theme'").replace("DARK", "'深色模式'" if zh else "'Dark theme'")
    if zh:
        answer = (f"{summary.get('active_days', 0)} 天投入标价 ${summary.get('list_price_usd', 0):,.2f} → "
                  f"{number(summary.get('repo_count', 0))} 个仓库 {number(summary.get('commits', 0))} 次提交。")
    else:
        answer = (f"${summary.get('list_price_usd', 0):,.2f} list price over {summary.get('active_days', 0)} days → "
                  f"{number(summary.get('commits', 0))} commits in {number(summary.get('repo_count', 0))} repositories.")
    chart_caption = tr("Each column uses its own scale. USD is a list-price equivalent. Tokens are output tokens.", "每列分别缩放。美元为标价等值。Token 为输出 token。")
    return ("<!doctype html>\n<!-- SPDX-License-Identifier: MIT; Copyright (c) 2026 Ninon -->\n"
            '<html lang="' + ('zh-CN' if zh else 'en') + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark">'
            '<title>shiptally · ' + tr("Account book", "账本") + '</title><style>' + CSS + '</style></head><body><main>'
            '<header><div><h1>shiptally</h1><p class="sub">' + tr("What did my tokens actually produce?", "我的 token 到底产出了什么？") + '</p>'
            '<p class="answer">' + _text(answer) + '</p></div>'
            '<button id="theme" type="button" aria-pressed="false">' + tr("Dark theme", "深色模式") + '</button></header>'
            '<p class="note price-note">' + price_note + ' ' + codex_note + '<br>' + dates + '</p>' + demo_note +
            '<section aria-labelledby="summary-title"><h2 id="summary-title">' + tr("Account book", "账本") + '</h2>'
            '<div class="t-account"><div class="account-side"><h3>' + tr("Input", "投入") + '</h3><dl>' + ''.join(inputs) + '</dl></div>'
            '<div class="account-side"><h3>' + tr("Output", "产出") + '</h3><dl>' + ''.join(outputs) + '</dl></div></div>'
            + author_note + '</section>'
            '<section aria-labelledby="projects-title"><h2 id="projects-title">' + tr("Projects", "项目") + '</h2>'
            '<div class="scroll" tabindex="0" role="region" aria-label="' + tr("Project ledger", "项目账本") + '"><table class="projects">'
            '<caption>' + tr("Sorted by list-price equivalent. Expand folders for working directories. Public status requires --github.", "按标价等值排序。展开目录可查看工作目录。公开状态需加 --github 查询。") + '</caption>' + colgroup +
            '<thead><tr>' + header + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></section>'
            '<section id="daily" aria-labelledby="daily-title"><h2 id="daily-title">' + tr("Daily spend and output", "每日投入与输出") + '</h2>' + daily_plot() + '</section>'
            '<p class="note">' + chart_caption + '</p>'
            '<div class="charts"><section id="monthly" aria-labelledby="monthly-title"><h2 id="monthly-title">' + tr("Monthly spend and output", "每月投入与输出") + '</h2>' + chart_table("monthly") + '</section>'
            + chart_table("daily") + '</div>'
            '<footer><p class="note">' + tr("Unknown means not checked or unavailable. Dates use UTC. Commits are not a measure of value.", "未知表示未查询或不可用。日期以 UTC 计。提交次数不代表价值。") + '</p>'
            + warnings + '</footer></main><script>' + script + '</script></body></html>\n')
