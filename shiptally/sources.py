# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Find log files; explicit sources may be directories or streamed archives."""

import os
from pathlib import Path


def _source_order(path):
    parts = Path(path).parts
    return ("archived_sessions" in parts, str(path))


def discover(extra=(), defaults=True):
    roots = [Path(value).expanduser() for value in extra]
    if defaults:
        claude = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).expanduser()
        codex = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
        roots.extend((claude / "projects", codex / "sessions", codex / "archived_sessions"))
    found = set()
    for root in roots:
        if root.is_dir():
            for directory, names, filenames in os.walk(root):
                names.sort()
                for name in filenames:
                    if name.endswith(".jsonl") and not name.startswith("._"):
                        found.add(Path(directory, name).absolute())
        elif root.is_file() and (root.name.endswith(".jsonl") or root.name.endswith(".tar.gz")):
            found.add(root.absolute())
    return sorted(found, key=_source_order)


def fallback_sid(path):
    path = Path(path)
    parts = path.parts
    if "subagents" in parts:
        index = parts.index("subagents")
        if index:
            return parts[index - 1].removesuffix(".jsonl")
    return path.stem
