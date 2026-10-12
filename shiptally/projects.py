# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Repository identity, a small project config format, and share-safe reports."""

import ast
import copy
import hashlib
import os
from pathlib import Path
import re
import subprocess
from collections import Counter


def _git(path, *args):
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def repository(path):
    """Return a common git-dir identity and the main worktree path, if present."""
    path = Path(path)
    if not path.exists() and "/.claude/worktrees/" in str(path):
        for ancestor in path.parents:
            if ancestor.is_dir():
                found = repository(ancestor)
                if found:
                    return found
    top = _git(path, "rev-parse", "--show-toplevel")
    if not top:
        return None
    common = _git(path, "rev-parse", "--git-common-dir")
    if not common:
        return None
    common = os.path.realpath(os.path.join(str(path), common))
    worktrees = _git(path, "worktree", "list", "--porcelain") or ""
    main = next((line[9:] for line in worktrees.splitlines()
                 if line.startswith("worktree ")), top)
    return {"key": "git:" + common, "path": os.path.realpath(main)}


def _value(text):
    if text in ("true", "false"):
        return text == "true"
    try:
        value = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        raise ValueError("Config values must be quoted strings, string lists, or booleans")
    if isinstance(value, str) or (isinstance(value, list) and
                                 all(isinstance(item, str) for item in value)):
        return value
    raise ValueError("Unsupported config value")


def _strip_comment(line):
    quote = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == "\\" and quote == '"':
            escaped = True
        elif char in "\"'":
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif char == "#" and quote is None:
            return line[:index]
    return line


def load_config(path):
    """Read [[projects]] with match, name, merge, and hide on Python 3.9+.

    The portable TOML subset accepts one-line string lists and quoted strings.
    A missing default config is handled by the caller; explicit missing files fail.
    """
    rows = []
    current = None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line == "[[projects]]":
            current = {}
            rows.append(current)
            continue
        match = re.fullmatch(r"(match|name|merge|hide)\s*=\s*(.+)", line)
        if current is None or not match:
            raise ValueError("Config supports only [[projects]] with match, name, merge, hide")
        key, value = match.groups()
        if key in current:
            raise ValueError("Duplicate project config key")
        current[key] = _value(value)
    for row in rows:
        if not isinstance(row.get("match"), list) or not row["match"]:
            raise ValueError("Each project rule needs a nonempty match string list")
        for key in ("name", "merge"):
            if key in row and (not isinstance(row[key], str) or not row[key]):
                raise ValueError("Project name and merge must be nonempty strings")
        if "hide" in row and not isinstance(row["hide"], bool):
            raise ValueError("Project hide must be true or false")
    return rows


class Mapper:
    def __init__(self, config=None):
        self.config = config or []
        self._cache = {}

    def _resolve_one(self, cwd):
        cwd = os.path.abspath(os.path.expanduser(str(cwd)))
        if cwd not in self._cache:
            home = os.path.abspath(str(Path.home()))
            repo = None if cwd == home else repository(cwd)
            if repo:
                self._cache[cwd] = {"key": repo["key"],
                                    "name": Path(repo["path"]).name,
                                    "repo_paths": [repo["path"]]}
            else:
                name = "~ (home folder)" if cwd == home else Path(cwd).name or "unknown"
                self._cache[cwd] = {"key": "path:" + cwd, "name": name,
                                    "repo_paths": []}
        return cwd, self._cache[cwd]

    def resolve(self, cwds):
        """Use the repository with most cwd records; break ties by first record."""
        counts = cwds if isinstance(cwds, dict) else Counter(cwds)
        candidates = {}
        totals = Counter()
        for cwd, count in counts.items():
            if not cwd or count <= 0:
                continue
            path, item = self._resolve_one(cwd)
            key = item["key"]
            if key not in candidates:
                candidates[key] = dict(item, paths=[], hidden=False)
            candidates[key]["paths"].append(path)
            totals[key] += count
        if not totals:
            return {"key": "unknown", "name": "unknown", "paths": [],
                    "repo_paths": [], "hidden": False}
        result = copy.deepcopy(candidates[max(totals, key=totals.get)])
        home_session = result["name"] == "~ (home folder)"
        aliases = set(result["paths"] + result["repo_paths"] +
                      [result["key"], result["name"]])
        aliases.update(Path(path).name for path in result["paths"])
        for rule in self.config:
            if not aliases.intersection(rule["match"]):
                continue
            if "merge" in rule:
                result["key"] = "merge:" + rule["merge"]
                result["name"] = rule.get("name", rule["merge"])
            elif "name" in rule:
                result["name"] = rule["name"]
            if "hide" in rule:
                result["hidden"] = rule["hide"]
        if home_session:
            result["name"] = "~ (home folder)"
        return result


def display_report(report):
    """Shorten the home prefix in all output strings, retaining internal git paths."""
    home = str(Path.home()).rstrip(os.sep)
    pattern = re.compile(re.escape(home) + r"(?=$|[/!\s\"'<>:,;)\]}]|[.?](?=\s|$))") if home else None

    def walk(value):
        if isinstance(value, dict):
            return {walk(key): walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str) and pattern:
            return pattern.sub(lambda _: "~", value)
        return copy.deepcopy(value)

    return walk(report)


def _pseudonym(value, prefix):
    return prefix + "-" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def redact(report):
    """Return a copy, replacing identities and paths without retaining a lookup."""
    sensitive = {"name", "key", "path", "paths", "repo_paths", "github_repos",
                 "github_public_repos", "github_unknown_repos", "github_remote_url",
                 "source_path", "source_file", "sources"}

    def hide_details(value):
        if isinstance(value, dict):
            return {key: hide_details(item) for key, item in value.items()}
        if isinstance(value, list):
            return [hide_details(item) for item in value]
        if isinstance(value, str):
            return "Details hidden by --redact" if value else value
        return copy.deepcopy(value)

    def walk(value, field=""):
        if field in ("diagnostics", "warnings", "errors"):
            return hide_details(value)
        if field == "github_stars" and isinstance(value, dict):
            return {_pseudonym(key, "path"): copy.deepcopy(item)
                    for key, item in value.items()}
        if isinstance(value, dict):
            return {key: walk(item, key) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item, field) for item in value]
        if isinstance(value, str) and field in sensitive:
            if field == "name" and value == "~ (home folder)":
                return value
            return _pseudonym(value, "project" if field in ("name", "key") else "path")
        return copy.deepcopy(value)

    return walk(report)
