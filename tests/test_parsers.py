# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon

import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from shiptally.cache import load_sources
from shiptally.parse_claude import parse_lines as claude
from shiptally.parse_codex import parse_lines as codex
from shiptally.sources import discover


TMP = Path(__file__).resolve().parents[2] / "_jobs" / "shiptally3" / "tmp"


def lines(*records):
    return [json.dumps(record) + "\n" for record in records]


def assistant(identifier="m1", output=10):
    return {"type": "assistant", "sessionId": "session-a", "cwd": "/example/project",
            "timestamp": "2026-01-01T12:00:00Z",
            "message": {"id": identifier, "model": "claude-opus-5-5",
                        "content": "PRIVATE_TEXT_MARKER",
                        "usage": {"input_tokens": 100, "output_tokens": output}}}


def token_record(total, last):
    return {"type": "event_msg", "timestamp": "2026-01-01T12:00:00Z", "payload": {
        "type": "token_count", "info": {"total_token_usage": dict(zip(
            ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"), total)),
            "last_token_usage": dict(zip(
            ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"), last))}}}


class ClaudeParserTests(unittest.TestCase):
    def test_usage_uses_last_iteration_and_keeps_only_counts(self):
        record = assistant()
        record["message"]["usage"] = {"input_tokens": 0, "iterations": [
            {"input_tokens": 999, "output_tokens": 999},
            {"input_tokens": 12, "output_tokens": 34, "private_text": "PRIVATE_TEXT_MARKER",
             "cache_creation": {"ephemeral_1h_input_tokens": 8, "private_text": "PRIVATE_TEXT_MARKER"}}]}
        result = claude(lines(record))
        self.assertEqual(result["events"][0]["usage"]["input_tokens"], 12)
        self.assertEqual(result["events"][0]["usage"]["output_tokens"], 34)
        self.assertEqual(result["events"][0]["usage"]["cache_creation"]["ephemeral_1h_input_tokens"], 8)
        self.assertNotIn("PRIVATE_TEXT_MARKER", json.dumps(result))

    def test_cwds_include_user_and_system_records(self):
        result = claude(lines(assistant(), {"type": "user", "cwd": "/example/second", "message": {"content": "secret"}},
                             {"type": "system", "cwd": "/example/second"}))
        self.assertEqual(result["cwds"], {"/example/project": 1, "/example/second": 2})
        self.assertEqual(result["sid"], "session-a")

    def test_streaming_duplicates_are_left_for_global_dedupe(self):
        result = claude(lines(assistant(output=1), assistant(output=10)), "file-session")
        self.assertEqual([event["id"] for event in result["events"]], ["m1", "m1"])
        self.assertEqual([event["usage"]["output_tokens"] for event in result["events"]], [1, 10])

    def test_bad_records_and_request_id_fallback(self):
        record = assistant()
        del record["message"]["id"]
        record["requestId"] = "request-a"
        result = claude(["bad", "[]", *lines(record)])
        self.assertEqual(result["events"][0]["id"], "request-a")
        record["message"]["model"] = "<synthetic>"
        self.assertEqual(claude(lines(record))["events"], [])


class CodexParserTests(unittest.TestCase):
    def test_direct_usage_wins_over_cumulative_records(self):
        result = codex(lines({"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z",
                              "payload": {"id": "cx-a", "cwd": "/example/project"}},
                             token_record((100, 20, 30, 0, 130), (100, 20, 30, 0, 130)),
                             {"type": "token_usage_record", "timestamp": "2026-01-01T12:00:00Z",
                              "payload": {"response_id": "response-a", "usage": {
                                  "input_tokens": 40, "cached_input_tokens": 10, "output_tokens": 7},
                                  "message": "PRIVATE_TEXT_MARKER"}}))
        self.assertEqual(result["sid"], "cx-a")
        self.assertEqual(result["events"], [{"id": "response-a", "ts": "2026-01-01T12:00:00Z",
                                             "input_tokens": 40, "cached_input_tokens": 10, "output_tokens": 7}])
        self.assertNotIn("PRIVATE_TEXT_MARKER", json.dumps(result))

    def test_fallback_first_last_repeated_total_and_reset(self):
        a = token_record((100, 20, 30, 5, 130), (10, 2, 3, 1, 13))
        b = token_record((150, 30, 40, 7, 190), (1, 0, 1, 0, 2))
        reset = token_record((5, 1, 2, 0, 7), (5, 1, 2, 0, 7))
        result = codex(lines(a, a, b, reset), "cx-fallback")
        self.assertEqual([event["output_tokens"] for event in result["events"]], [3, 10, 2])
        self.assertEqual([event["input_tokens"] for event in result["events"]], [10, 50, 5])
        self.assertEqual([event["cached_input_tokens"] for event in result["events"]], [2, 10, 1])
        self.assertTrue(all(event["id"] is None for event in result["events"]))

    def test_reset_in_reasoning_field_also_uses_last(self):
        first = token_record((100, 20, 30, 5, 130), (10, 2, 3, 1, 13))
        second = token_record((110, 22, 33, 0, 143), (4, 1, 2, 0, 6))
        result = codex(lines(first, second))
        self.assertEqual(result["events"][1]["output_tokens"], 2)

    def test_turn_context_working_directories(self):
        result = codex(lines({"type": "session_meta", "payload": {"id": "cx-a", "cwd": "/example/one"}},
                             {"type": "turn_context", "payload": {"cwd": "/example/two"}},
                             {"type": "turn_context", "payload": {"cwd": "/example/two"}}))
        self.assertEqual(result["cwds"], {"/example/one": 1, "/example/two": 2})


class SourceCacheTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=str(TMP))
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, records):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(lines(*records)), encoding="utf-8")
        return path

    def test_subagent_and_cache_hit_and_change(self):
        path = self.write("projects/project/parent-session/subagents/agent-a.jsonl", [assistant()])
        entries, diagnostics = load_sources([path], self.root / "cache")
        self.assertEqual(entries[0]["sid"], "parent-session")
        self.assertEqual(diagnostics["parsed"], 1)
        entries_again, diagnostics = load_sources([path], self.root / "cache")
        self.assertEqual(entries, entries_again)
        self.assertEqual(diagnostics["cache_hits"], 1)
        self.assertEqual(diagnostics["parsed"], 0)
        cache_text = "".join(item.read_text() for item in (self.root / "cache").iterdir())
        self.assertNotIn("PRIVATE_TEXT_MARKER", cache_text)
        path.write_text("".join(lines(assistant(output=1234))), encoding="utf-8")
        changed, diagnostics = load_sources([path], self.root / "cache")
        self.assertEqual(diagnostics["parsed"], 1)
        self.assertEqual(changed[0]["events"][0]["usage"]["output_tokens"], 1234)

    def test_archive_streams_both_kinds_without_extracting(self):
        archive_path = self.root / "logs.tar.gz"
        codex_record = {"type": "token_usage_record", "timestamp": "2026-01-01T00:00:00Z", "payload": {
            "response_id": "response-a", "usage": {"output_tokens": 5}}}
        with tarfile.open(archive_path, "w:gz") as archive:
            for name, record in (("../../outside.jsonl", assistant()), ("sessions/codex.jsonl", codex_record)):
                data = "".join(lines(record)).encode()
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        entries, diagnostics = load_sources([archive_path], None)
        self.assertEqual({entry["kind"] for entry in entries}, {"claude", "codex"})
        self.assertEqual(diagnostics["parsed"], 1)
        self.assertEqual(list(self.root.iterdir()), [archive_path])

    def test_environment_roots_and_explicit_sources(self):
        cc = self.write("claude/projects/a/main.jsonl", [assistant()])
        cx = self.write("codex/archived_sessions/archived.jsonl", [{"type": "session_meta", "payload": {"id": "cx"}}])
        with patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": str(self.root / "claude"), "CODEX_HOME": str(self.root / "codex")}):
            self.assertEqual(set(discover()), {cc, cx})
            self.assertEqual(discover([cc], defaults=False), [cc])

    def test_live_codex_file_precedes_same_archive_member(self):
        record = token_record((100, 20, 30, 5, 130), (10, 2, 3, 1, 13))
        live = self.write("codex/sessions/thread.jsonl", [record])
        archive_path = self.root / "duplicate.tar.gz"
        data = "".join(lines(record)).encode()
        with tarfile.open(archive_path, "w:gz") as archive:
            member = tarfile.TarInfo(".codex/sessions/thread.jsonl")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        entries, _ = load_sources([archive_path, live], None)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source"], str(live))

    def test_multi_file_first_parse_uses_metadata_only(self):
        paths = [self.write("source%d.jsonl" % n, [assistant(identifier="m%d" % n)]) for n in range(2)]
        entries, diagnostics = load_sources(paths, None)
        self.assertEqual(diagnostics["parsed"], 2)
        self.assertEqual(len(entries), 2)
        self.assertNotIn("PRIVATE_TEXT_MARKER", json.dumps(entries))


if __name__ == "__main__":
    unittest.main()
