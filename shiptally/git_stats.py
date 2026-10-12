# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Commit counts and optional GitHub metadata. Network access is opt-in."""

import datetime as dt
import json
import re
import shutil
import subprocess
import urllib.request

from .projects import repository


def _run(path, args):
    try:
        process = subprocess.run(["git", "-C", str(path), *args],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 timeout=60)
        if process.returncode == 0:
            return process.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _boundary(value, end=False):
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if len(value) == 10 and end:
        parsed += dt.timedelta(days=1, microseconds=-1)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def _github_name(remote):
    match = re.fullmatch(r"(?:(?:https?://|ssh://|git://)(?:[^/@]+@)?github\.com/|(?:[^/@]+@)?github\.com[:/])([^/\s]+/[^/\s]+?)(?:\.git)?/?", remote)
    return match.group(1) if match else None


def _github_metadata(name):
    """Fetch only public repository metadata, without storing credentials."""
    try:
        if shutil.which("gh"):
            process = subprocess.run(["gh", "api", "repos/" + name],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, timeout=10)
            if process.returncode != 0:
                return None
            data = json.loads(process.stdout)
        else:
            request = urllib.request.Request(
                "https://api.github.com/repos/" + name,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "shiptally"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get("private"), bool):
            return None
        stars = data.get("stargazers_count")
        if not isinstance(stars, int) or isinstance(stars, bool) or stars < 0:
            return None
        return {"public": not data["private"], "stars": stars}
    except (OSError, ValueError, subprocess.TimeoutExpired, KeyError):
        return None


def collect(paths, since=None, until=None, author=None, github=False, metadata_cache=None,
            all_authors=False):
    start, end = _boundary(since), _boundary(until, True)
    repos = {}
    for path in paths:
        repo = repository(path)
        if repo:
            repos.setdefault(repo["key"], repo["path"])
    commits, added, removed = 0, 0, 0
    git_errors = 0
    missing_emails = 0
    github_repos = set()
    for path in repos.values():
        email = None
        if author is None and not all_authors:
            # Effective config includes the repository override and global fallback.
            email = (_run(path, ["config", "user.email"]) or "").strip()
            if not email:
                missing_emails += 1
        args = ["log", "--all", "--format=%x1e%H%x00%ct%x00%ae", "--numstat", "-z", "--no-renames"]
        if author is not None:
            args.append("--author=" + author)
        log = _run(path, args)
        if log is None:
            # git log fails on repositories that have no commits too.
            count = _run(path, ["rev-list", "--all", "--count"])
            if count is None or count.strip() != "0":
                git_errors += 1
            log = ""
        for block in log.split("\x1e"):
            if not block:
                continue
            header, _, rest = block.partition("\x00")
            timestamp, _, stats = rest.partition("\x00")
            author_email, _, stats = stats.partition("\x00")
            try:
                stamp = int(timestamp.strip())
            except ValueError:
                continue
            if (start is not None and stamp < start) or (end is not None and stamp > end):
                continue
            if author is None and not all_authors and (not email or author_email != email):
                continue
            commits += 1
            for entry in stats.split("\x00"):
                columns = entry.lstrip("\n").split("\t", 2)
                if len(columns) == 3 and columns[0].isdigit() and columns[1].isdigit():
                    added += int(columns[0])
                    removed += int(columns[1])
        for line in (_run(path, ["remote", "-v"]) or "").splitlines():
            columns = line.split()
            if len(columns) > 1:
                name = _github_name(columns[1])
                if name:
                    github_repos.add(name)
    public, stars = (None if github_repos else False), None
    public_repos, unknown_repos, github_stars = [], [], {}
    if github and github_repos:
        cache = metadata_cache if metadata_cache is not None else {}
        metadata = []
        for name in sorted(github_repos):
            if name not in cache:
                cache[name] = _github_metadata(name)
            item = cache[name]
            metadata.append(item)
            if item is None:
                unknown_repos.append(name)
            elif item["public"]:
                public_repos.append(name)
                github_stars[name] = item["stars"]
        known = [item for item in metadata if item is not None]
        if any(item["public"] for item in known):
            public = True
        elif len(known) == len(metadata):
            public = False
        if len(known) == len(metadata):
            stars = sum(item["stars"] for item in known if item["public"])
    elif github_repos:
        unknown_repos = sorted(github_repos)
    rule = ("Git --author pattern: " + author if author is not None else
            "All authors (--all-authors)" if all_authors else
            "Exact author email = git config user.email (repository, then global)")
    return {"author_rule": rule, "missing_author_emails": missing_emails,
            "github_checked": github,
            "commits": None if git_errors else commits,
            "lines_added": None if git_errors else added,
            "lines_removed": None if git_errors else removed, "git_errors": git_errors,
            "github_remote": bool(github_repos), "github_repos": sorted(github_repos),
            "github_public_repos": public_repos, "github_stars": github_stars,
            "github_unknown_repos": unknown_repos,
            "public": public, "stars": stars, "repo_count": len(repos)}
