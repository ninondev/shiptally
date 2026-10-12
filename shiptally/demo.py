# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Seeded synthetic usage with precomputed fictional git statistics, all in memory."""
from datetime import date, timedelta
from random import Random

from . import pricing


SEED = 73060
START = date(2026, 8, 1)
DAYS = 60
LABEL = "Synthetic demo data"
AUTHOR_RULE = "Synthetic author; precomputed git statistics"
# Name, kind, active days, last day offset, sessions/day, token scale, git totals.
PROFILES = (
    ("menu-bar-clock", "menu-bar app", DAYS, DAYS - 1, (2, 4), 1.0, (86, 12840, 4930)),
    ("archive-cli", "CLI", 44, 59, (1, 3), .8, (63, 7240, 2110)),
    ("build-dashboard", "web dashboard", 48, 59, (2, 5), 1.5, (74, 19630, 8240)),
    ("garden-game-mod", "game mod", 22, 54, (1, 3), .7, (28, 4830, 1670)),
    ("abandoned-search", "abandoned experiment", 8, 17, (2, 4), 2.2, (0, 0, 0)),
    ("tiny-sequence-lib", "library", 18, 59, (1, 2), .08, (132, 2380, 910)),
    ("research-notebook", "research notebook", 36, 59, (1, 4), 1.2, (19, 6120, 2470)),
)


def sample():
    rng = Random(SEED)
    projects, daily = [], {}
    fields = ("list_price_usd", "claude_output_tokens", "codex_output_tokens")
    for name, kind, active, end, sessions, scale, git in PROFILES:
        # Pin both endpoints, then pick the remaining active days without replacement.
        offsets = sorted([0, end] + rng.sample(range(1, end), active - 2))
        root = "~/Projects/" + name
        row = {"name": name, "key": "demo:" + name, "demo_kind": kind,
               "paths": [root, root + "/src"], "repo_paths": [root],
               "list_price_usd": 0.0, "claude_list_price_usd": 0.0,
               "codex_list_price_usd": None, "claude_output_tokens": 0,
               "codex_output_tokens": 0, "sessions": 0, "active_days": active,
               "first_activity": START.isoformat(),
               "last_activity": (START + timedelta(days=end)).isoformat(),
               "commits": git[0], "lines_added": git[1], "lines_removed": git[2],
               "repo_count": 1, "git_errors": 0, "missing_author_emails": 0,
               "author_rule": AUTHOR_RULE, "github_checked": False,
               "github_remote": False, "github_repos": [], "github_public_repos": [],
               "github_unknown_repos": [], "github_stars": {}, "public": False,
               "stars": None}
        for offset in offsets:
            day = (START + timedelta(days=offset)).isoformat()
            bucket = daily.setdefault(day, dict(day=day, list_price_usd=0.0,
                                               claude_output_tokens=0, codex_output_tokens=0))
            for _ in range(rng.randint(*sessions)):
                output = int(rng.randint(8000, 36000) * scale)
                row["sessions"] += 1
                if rng.random() < .6:
                    usage = {"input_tokens": int(rng.randint(20000, 80000) * scale),
                             "output_tokens": output,
                             "cache_read_input_tokens": int(rng.randint(400000, 1800000) * scale),
                             "cache_creation_input_tokens": int(rng.randint(30000, 160000) * scale)}
                    model = "claude-opus-5-5" if rng.random() < .65 else "claude-sonnet-5-5"
                    usd = pricing.cost_of(model, usage)
                    row["claude_list_price_usd"] += usd
                    row["list_price_usd"] += usd
                    bucket["list_price_usd"] += usd
                    token_key = "claude_output_tokens"
                else:
                    token_key = "codex_output_tokens"
                row[token_key] += output
                bucket[token_key] += output
        for field in ("list_price_usd", "claude_list_price_usd"):
            row[field] = round(row[field], 8)
        projects.append(row)
    monthly = {}
    for day, bucket in sorted(daily.items()):
        bucket["list_price_usd"] = round(bucket["list_price_usd"], 8)
        month = day[:7]
        totals = monthly.setdefault(month, dict(month=month, list_price_usd=0.0,
                                               claude_output_tokens=0, codex_output_tokens=0))
        for field in fields:
            totals[field] += bucket[field]
    for totals in monthly.values():
        totals["list_price_usd"] = round(totals["list_price_usd"], 8)
    summary = {field: sum(row[field] for row in projects) for field in
               fields + ("sessions", "commits", "lines_added", "lines_removed", "repo_count")}
    summary["list_price_usd"] = round(summary["list_price_usd"], 8)
    summary.update(active_days=len(daily), first_activity=min(daily), last_activity=max(daily),
                   public=0, stars=None, github_checked=False, git_errors=0,
                   missing_author_emails=0, author_rule=AUTHOR_RULE)
    return {"schema_version": 1, "demo": True, "demo_label": LABEL,
            "demo_seed": SEED, "demo_git_method": "Precomputed fictional commits and line counts; no git scans.",
            "basis": "USD list-price equivalent; not a bill. Subscriptions differ.",
            "pricing": {"source": pricing.PRICE_SOURCE, "checked_date": pricing.CHECKED_DATE,
                        "check_method": "Copied from a local price snapshot; not checked online.",
                        "codex": "tokens only"},
            "window": {"since": min(daily), "until": max(daily), "timezone": "UTC"},
            "summary": summary,
            "projects": sorted(projects, key=lambda row: (-row["list_price_usd"], row["name"])),
            "daily": [daily[day] for day in sorted(daily)],
            "monthly": [monthly[month] for month in sorted(monthly)], "warnings": [],
            "diagnostics": {"files": 0, "parsed": 0, "cache_hits": 0, "skipped": 0}}
