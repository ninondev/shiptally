# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
"""Join sanitized usage events to repositories, without retaining conversations."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from . import pricing, git_stats


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except ValueError:
        return None


def build(entries, mapper, since=None, until=None, author=None, github=False, codex_prices=None,
          all_authors=False):
    sessions = {}
    for ent in entries:
        sk = (ent["kind"], ent["sid"])
        session = sessions.setdefault(sk, {"cwds": Counter(), "events": []})
        session["cwds"].update(ent["cwds"])
        session["events"].extend((e, ent.get("birth", 0)) for e in ent["events"])
    best = {}
    seen = set()
    chosen = []
    for sk, sess in sessions.items():
        for event, birth in sess["events"]:
            if sk[0] == "claude":
                key = (event["usage"].get("output_tokens", 0), -birth)
                old = best.get(event["id"])
                if old is None or key > old[0]:
                    best[event["id"]] = (key, sk, event)
            else:
                rid = event.get("id")
                if rid and rid in seen:
                    continue
                if rid:
                    seen.add(rid)
                chosen.append((sk, event))
    chosen.extend((sk, event) for _, sk, event in best.values())
    rows, daily, warnings = {}, {}, set()
    for sk, event in chosen:
        dt = timestamp(event.get("ts"))
        if dt is None:
            continue
        day = dt.date().isoformat()
        if (since and day < since) or (until and day > until):
            continue
        project = mapper.resolve(sessions[sk]["cwds"])
        if project["hidden"]:
            continue
        key = project["key"]
        row = rows.setdefault(key, dict(project, list_price_usd=0.0, claude_list_price_usd=0.0,
            codex_list_price_usd=None if codex_prices is None else 0.0,
            claude_output_tokens=0, codex_output_tokens=0, _sessions=set(), _days=set(),
            first_activity=day, last_activity=day))
        row["paths"] = sorted(set(row["paths"]) | set(project["paths"]))
        row["repo_paths"] = sorted(set(row["repo_paths"]) | set(project["repo_paths"]))
        bucket = daily.setdefault(day, {"day": day, "list_price_usd": 0.0,
            "claude_output_tokens": 0, "codex_output_tokens": 0})
        if sk[0] == "claude":
            usd = pricing.cost_of(event["model"], event["usage"])
            if not pricing.is_known_model(event["model"]):
                warnings.add("Unknown Claude models use the Opus 5.5 list-price fallback.")
            out = event["usage"].get("output_tokens", 0)
            row["claude_list_price_usd"] += usd
            token_key = "claude_output_tokens"
        else:
            usd = pricing.cost_codex(event, codex_prices) if codex_prices is not None else 0.0
            if codex_prices is not None:
                row["codex_list_price_usd"] += usd
            out = event["output_tokens"]
            token_key = "codex_output_tokens"
        row["list_price_usd"] += usd
        bucket["list_price_usd"] += usd
        row[token_key] += out
        bucket[token_key] += out
        row["_sessions"].add(sk)
        row["_days"].add(day)
        row["first_activity"] = min(row["first_activity"], day)
        row["last_activity"] = max(row["last_activity"], day)
    first = min(daily) if daily else None
    last = max(daily) if daily else None
    window = {"since": since or first, "until": until or last, "timezone": "UTC"}
    repos = set()
    metadata_cache = {}
    for row in rows.values():
        repos.update(row["repo_paths"])
        row["sessions"] = len(row.pop("_sessions"))
        row["active_days"] = len(row.pop("_days"))
        row.update(git_stats.collect(row["repo_paths"], window["since"], window["until"], author, github, metadata_cache, all_authors))
        row.pop("hidden", None)
        for field in ("list_price_usd", "claude_list_price_usd", "codex_list_price_usd"):
            if row[field] is not None:
                row[field] = round(row[field], 8)
    # Shared repositories across config groups count once in the summary.
    total_git = git_stats.collect(sorted(repos), window["since"], window["until"], author, github, metadata_cache, all_authors)
    if total_git["missing_author_emails"]:
        warnings.add("No git user.email configured for " + str(total_git["missing_author_emails"]) +
                     " repositories; no commits counted there. Set user.email or use --all-authors / --author.")
    public_slugs, stars_by_slug = set(), {}
    unknown_public = False
    for row in rows.values():
        if row.get("github_unknown_repos") or (row["github_remote"] and row["public"] is None):
            unknown_public = True
        public_slugs.update(row.get("github_public_repos", []))
        if row["stars"] is not None:
            # A remote may be shared by two local clones: use row metadata if supplied.
            for slug, count in row.get("github_stars", {}).items():
                stars_by_slug[slug] = count
    known_stars = sum(stars_by_slug.values()) if stars_by_slug else sum(r["stars"] or 0 for r in rows.values())
    summary = dict(total_git, list_price_usd=round(sum(r["list_price_usd"] for r in rows.values()), 8),
        claude_output_tokens=sum(r["claude_output_tokens"] for r in rows.values()),
        codex_output_tokens=sum(r["codex_output_tokens"] for r in rows.values()),
        sessions=sum(r["sessions"] for r in rows.values()), active_days=len(daily),
        first_activity=first, last_activity=last, public=None if unknown_public else len(public_slugs),
        stars=None if not github or unknown_public else known_stars)
    months = {}
    for b in daily.values():
        month = b["day"][:7]
        m = months.setdefault(month, {"month": month, "list_price_usd": 0.0,
            "claude_output_tokens": 0, "codex_output_tokens": 0})
        for field in ("list_price_usd", "claude_output_tokens", "codex_output_tokens"):
            m[field] += b[field]
    return {"schema_version": 1, "basis": "USD list-price equivalent; not a bill. Subscriptions differ.",
        "pricing": {"source": pricing.PRICE_SOURCE, "checked_date": pricing.CHECKED_DATE,
            "check_method": "Copied from a local price snapshot; not checked online.",
            "codex": "user-supplied" if codex_prices else "tokens only"},
        "window": window, "summary": summary,
        "projects": sorted(rows.values(), key=lambda r: (-r["list_price_usd"], r["name"])),
        "daily": [daily[k] for k in sorted(daily)], "monthly": [months[k] for k in sorted(months)],
        "warnings": sorted(warnings)}
