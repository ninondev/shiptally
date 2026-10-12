# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Create synthetic logs and throwaway git repositories in a new directory."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def git(root, *args, day=None):
    env = os.environ.copy()
    if day:
        env.update(GIT_AUTHOR_DATE=day + "T12:00:00Z", GIT_COMMITTER_DATE=day + "T12:00:00Z")
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def claude(mid, sid, cwd, day, fresh, output):
    return {"type": "assistant", "sessionId": sid, "cwd": str(cwd),
        "timestamp": day + "T12:00:00Z", "message": {"id": mid, "model": "claude-opus-5-5",
        "usage": {"input_tokens": fresh, "output_tokens": output},
        "content": "Synthetic message. It must never appear in reports or cache."}}


def write(root, name, rows):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def create(root):
    root = Path(root).absolute()
    root.mkdir(parents=True, exist_ok=False)
    a, b = root / "repos" / "alpha", root / "repos" / "beta"
    for repo in (a, b):
        repo.mkdir(parents=True)
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Example")
        git(repo, "config", "user.email", "284425649+ninondev@users.noreply.github.com")
        (repo / "code.txt").write_text("first\nsecond\n", encoding="utf-8")
        git(repo, "add", "code.txt")
        git(repo, "commit", "-m", "Synthetic first commit", day="2026-09-01")
    (a / "code.txt").write_text("first\nchanged\nthird\n", encoding="utf-8")
    git(a, "add", "code.txt")
    git(a, "commit", "-m", "Synthetic second commit", day="2026-09-02")
    one = claude("m-alpha", "cl-alpha", a, "2026-09-01", 1_000_000, 100_000)
    write(root, "logs/claude/projects/alpha/cl-alpha.jsonl", [one])
    write(root, "logs/claude/projects/alpha/cl-alpha/subagents/agent.jsonl", [
        claude("m-sub", "sub-id", a, "2026-09-02", 100_000, 15_000)])
    write(root, "logs/claude/projects/alpha/resume.jsonl", [dict(one)])
    write(root, "logs/claude/projects/beta/cl-beta.jsonl", [
        claude("m-beta", "cl-beta", b, "2026-10-01", 100_000, 10_000)])
    meta = {"type": "session_meta", "timestamp": "2026-09-01T11:00:00Z",
            "payload": {"id": "cx-alpha", "cwd": str(a)}}
    token = {"type": "token_usage_record", "timestamp": "2026-09-01T12:30:00Z",
            "payload": {"response_id": "r-alpha", "usage": {
                "input_tokens": 200_000, "cached_input_tokens": 50_000, "output_tokens": 40_000}}}
    write(root, "logs/codex/sessions/alpha.jsonl", [meta, token])
    write(root, "logs/codex/archived_sessions/resume.jsonl", [meta, token])
    write(root, "logs/codex/sessions/beta.jsonl", [
        {"type": "session_meta", "timestamp": "2026-10-01T11:00:00Z", "payload": {"id": "cx-beta", "cwd": str(b)}},
        {"type": "event_msg", "timestamp": "2026-10-01T12:30:00Z", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 100_000, "output_tokens": 20_000, "total_tokens": 120_000},
            "last_token_usage": {"input_tokens": 100_000, "output_tokens": 20_000, "total_tokens": 120_000}}}}])
    (root / "config.toml").write_text("", encoding="utf-8")
    (root / "codex-prices.json").write_text(json.dumps({"input": 2, "cached_input": 0.5, "output": 8}), encoding="utf-8")
    return root


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    create(p.parse_args().directory)
