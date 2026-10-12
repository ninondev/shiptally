# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
"""Per-file metadata cache. No prompts, replies, or tool output are kept."""

import hashlib
import itertools
import json
import multiprocessing
import os
import tarfile
from pathlib import Path

from . import parse_claude, parse_codex
from .sources import fallback_sid


CACHE_VERSION = 1


def _parse(lines, name, birth, source):
    prefix = []
    kind = None
    iterator = iter(lines)
    for line in iterator:
        prefix.append(line)
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        tag = record.get("type")
        if tag in ("session_meta", "turn_context", "token_usage_record", "event_msg", "response_item"):
            kind = "codex"
        elif "sessionId" in record or tag in ("assistant", "user", "attachment", "system", "queue-operation"):
            kind = "claude"
        if kind:
            break
    if kind is None:
        return None
    parser = parse_claude if kind == "claude" else parse_codex
    sid = fallback_sid(name)
    entry = parser.parse_lines(itertools.chain(prefix, iterator), sid=sid)
    if kind == "claude" and "subagents" in Path(name).parts:
        entry["sid"] = sid
    entry.update(source=source, birth=birth)
    return entry


def _parse_file(task):
    path, birth = task
    entries = []
    try:
        if path.endswith(".tar.gz"):
            with tarfile.open(path, "r|gz") as archive:
                for member in archive:
                    name = member.name
                    if not member.isfile() or not name.endswith(".jsonl") or Path(name).name.startswith("._"):
                        continue
                    stream = archive.extractfile(member)
                    if stream is None:
                        continue
                    with stream:
                        entry = _parse((line.decode("utf-8", "replace") for line in stream), name,
                                       member.mtime, path + "!" + name)
                    if entry:
                        entries.append(entry)
        else:
            with open(path, encoding="utf-8", errors="replace") as stream:
                entry = _parse(stream, path, birth, path)
            if entry:
                entries.append(entry)
        return path, entries, None
    except (OSError, ValueError, tarfile.TarError):
        return path, [], "unreadable"


def _cache_path(cache_dir, path):
    digest = hashlib.sha256(path.encode("utf-8", "replace")).hexdigest()
    return cache_dir / (digest + ".json")


def _codex_relative(source):
    name = source.split("!", 1)[-1]
    parts = Path(name).parts
    for marker in ("sessions", "archived_sessions"):
        if marker in parts:
            return "/".join(parts[parts.index(marker):])
    return name if "!" in source else None


def _atomic_json(path, payload):
    temporary = path.with_name(path.name + ".tmp." + str(os.getpid()))
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(str(temporary), str(path))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_sources(paths, cache_dir=None):
    """Return entries and parse counts. None disables all cache reads and writes."""
    paths = [str(Path(path).absolute()) for path in paths]
    diagnostics = {"files": len(paths), "parsed": 0, "cache_hits": 0, "skipped": 0}
    cache_dir = Path(cache_dir) if cache_dir is not None else None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
    found, pending, metadata = {}, [], {}
    for path in paths:
        try:
            stat = os.stat(path)
        except OSError:
            diagnostics["skipped"] += 1
            continue
        signature = {"version": CACHE_VERSION, "path": path,
                     "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        metadata[path] = signature
        cached = None
        if cache_dir is not None:
            try:
                with _cache_path(cache_dir, path).open(encoding="utf-8") as stream:
                    payload = json.load(stream)
                if payload.get("metadata") == signature and isinstance(payload.get("entries"), list):
                    cached = payload["entries"]
            except (OSError, ValueError, AttributeError):
                pass
        if cached is not None:
            found[path] = cached
            diagnostics["cache_hits"] += 1
        else:
            pending.append((path, getattr(stat, "st_birthtime", stat.st_mtime)))
    if pending:
        pending.sort(key=lambda item: -metadata[item[0]]["size"])
        # A spawned worker only imports this module; CLI execution is guarded in __main__.
        if len(pending) == 1:
            parsed = [_parse_file(pending[0])]
        else:
            with multiprocessing.get_context("spawn").Pool(min(4, len(pending))) as pool:
                parsed = list(pool.imap_unordered(_parse_file, pending, chunksize=1))
        for path, entries, error in parsed:
            diagnostics["parsed"] += 1
            if error:
                diagnostics["skipped"] += 1
                continue
            found[path] = entries
            if cache_dir is not None:
                _atomic_json(_cache_path(cache_dir, path), {"metadata": metadata[path], "entries": entries})
    entries = [entry for path in paths for entry in found.get(path, [])]
    # Live sessions precede archived sessions and archives for response-id dedupe.
    entries.sort(key=lambda entry: ("!" in entry["source"],
                                   "archived_sessions" in entry["source"].split("/"), entry["source"]))
    retained, seen_relative = [], set()
    for entry in entries:
        relative = _codex_relative(entry["source"]) if entry["kind"] == "codex" else None
        if relative is not None:
            if "!" in entry["source"] and relative in seen_relative:
                continue
            seen_relative.add(relative)
        retained.append(entry)
    return retained, diagnostics
