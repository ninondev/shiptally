# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
"""Reduce Claude Code records to usage metadata without keeping message text."""

import json


TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens")
CACHE_FIELDS = ("ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens")


def token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def pick_usage(usage):
    iterations = usage.get("iterations")
    if isinstance(iterations, list) and iterations and isinstance(iterations[-1], dict):
        usage = iterations[-1]
    result = {key: token_count(usage.get(key)) for key in TOKEN_FIELDS}
    creation = usage.get("cache_creation")
    creation = creation if isinstance(creation, dict) else {}
    result["cache_creation"] = {key: token_count(creation.get(key)) for key in CACHE_FIELDS}
    return result


def parse_lines(lines, sid="unknown"):
    entry = {"kind": "claude", "sid": sid, "cwds": {}, "first_ts": None, "events": []}
    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        session = record.get("sessionId")
        if isinstance(session, str) and session:
            entry["sid"] = session
        cwd = record.get("cwd")
        if isinstance(cwd, str) and cwd:
            entry["cwds"][cwd] = entry["cwds"].get(cwd, 0) + 1
        ts = record.get("timestamp")
        if isinstance(ts, str) and ts:
            if entry["first_ts"] is None or ts < entry["first_ts"]:
                entry["first_ts"] = ts
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage, model = message.get("usage"), message.get("model")
        identifier = message.get("id") or record.get("requestId")
        if not (isinstance(usage, dict) and usage and isinstance(model, str) and model
                and not model.startswith("<") and isinstance(identifier, str) and identifier
                and isinstance(ts, str) and ts):
            continue
        entry["events"].append({"id": identifier, "ts": ts, "model": model,
                                "usage": pick_usage(usage)})
    return entry
