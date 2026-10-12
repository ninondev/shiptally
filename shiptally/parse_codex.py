# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Read Codex usage records, with the cumulative-token fallback."""

import json

from .parse_claude import token_count


FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens",
          "reasoning_output_tokens", "total_tokens")


def _event(ts, identifier, usage):
    return {"id": identifier, "ts": ts,
            **{key: token_count(usage.get(key)) for key in FIELDS[:3]}}


def parse_lines(lines, sid="unknown"):
    entry = {"kind": "codex", "sid": sid, "cwds": {}, "first_ts": None, "events": []}
    direct, cumulative = [], []
    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        ts = record.get("timestamp")
        ts = ts if isinstance(ts, str) else None
        if ts and (entry["first_ts"] is None or ts < entry["first_ts"]):
            entry["first_ts"] = ts
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd:
            entry["cwds"][cwd] = entry["cwds"].get(cwd, 0) + 1
        kind = record.get("type")
        if kind == "session_meta":
            if isinstance(payload.get("id"), str) and payload["id"]:
                entry["sid"] = payload["id"]
        elif kind == "token_usage_record":
            usage = payload.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            identifier = payload.get("response_id")
            identifier = identifier if isinstance(identifier, str) and identifier else None
            direct.append(_event(ts, identifier, usage))
        elif kind == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info")
            if not isinstance(info, dict) or not info:
                continue
            total, last = info.get("total_token_usage"), info.get("last_token_usage")
            total = total if isinstance(total, dict) else {}
            last = last if isinstance(last, dict) else {}
            cumulative.append((ts, tuple(token_count(total.get(key)) for key in FIELDS),
                               tuple(token_count(last.get(key)) for key in FIELDS)))
    if direct:
        entry["events"] = direct
    else:
        previous = None
        for ts, total, last in cumulative:
            delta = last if previous is None else tuple(a - b for a, b in zip(total, previous))
            if any(value < 0 for value in delta):
                delta = last
            if total != previous:
                entry["events"].append(_event(ts, None, dict(zip(FIELDS, delta))))
            previous = total
    return entry
