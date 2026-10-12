# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
import argparse
import json
import math
import os
import sys
from datetime import date
from pathlib import Path
from .cache import load_sources
from .sources import discover
from .projects import Mapper, load_config, redact, display_report
from .report import build
from .render_text import render
from .render_html import render as render_html


def valid_date(text):
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError("Use a date such as 2026-09-01.")


def read_prices(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"input", "cached_input", "output"}:
        raise ValueError("Codex prices need input, cached_input and output rates in USD per million tokens.")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in value.values()):
        raise ValueError("Codex prices must be finite non-negative numbers.")
    return value


def main(argv=None):
    p = argparse.ArgumentParser(description="What did your tokens produce? Join local AI usage to git output.")
    p.add_argument("--source", action="append", default=[], metavar="PATH", help="Add a log directory, JSONL or tar.gz; repeat to combine.")
    p.add_argument("--no-default-sources", action="store_true", help="Read only explicit sources; skip the default log roots.")
    p.add_argument("--config", type=Path, help="Project rename, merge and hide rules in TOML.")
    p.add_argument("--since", type=valid_date, help="First included UTC date.")
    p.add_argument("--until", type=valid_date, help="Last included UTC date.")
    authors = p.add_mutually_exclusive_group()
    authors.add_argument("--author", help="Git author regular expression; overrides the default email filter.")
    authors.add_argument("--all-authors", action="store_true", help="Count every author; default: exact git user.email.")
    p.add_argument("--verbose", action="store_true", help="List working directories below the text table.")
    p.add_argument("--demo", action="store_true", help="Render the packaged synthetic sample without reading logs, config or cache.")
    p.add_argument("--github", action="store_true", help="Allow network to check public status and stars.")
    p.add_argument("--codex-prices", metavar="JSON", help="User rates: input, cached_input, output; USD per million.")
    p.add_argument("--redact", action="store_true", help="Replace project names, paths and remotes with stable pseudonyms.")
    p.add_argument("--no-cache", action="store_true", help="Parse again without reading or writing cache.")
    p.add_argument("--lang", choices=("en", "zh"), default="en")
    output = p.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print the versioned JSON report.")
    output.add_argument("--html", type=Path, metavar="FILE", help="Write one offline HTML file.")
    args = p.parse_args(argv)
    if args.since and args.until and args.since > args.until:
        p.error("--since must be on or before --until.")
    if args.demo and (args.source or args.config or args.since or args.until or
                      args.author is not None or args.all_authors or args.github or args.codex_prices):
        p.error("--demo uses fixed sample data; combine it only with output, language, verbose or redaction options.")
    try:
        if args.demo:
            from .demo import sample
            data = sample()
        else:
            data = read_report(args)
        if args.redact:
            data = redact(data)
        data = display_report(data)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.html:
            args.html.write_text(render_html(data, args.lang), encoding="utf-8")
            print(render(data, args.lang, args.verbose))
        else:
            print(render(data, args.lang, args.verbose))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        # Errors may contain transcript paths; share mode omits them.
        message = "Could not read inputs or write the report." if args.redact else str(exc)
        print("shiptally: " + display_report(message), file=sys.stderr)
        return 1


def read_report(args):
    config_path = args.config or Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "shiptally" / "config.toml"
    rules = load_config(config_path) if config_path.exists() else []
    if args.config and not config_path.exists():
        raise ValueError("The requested config file does not exist.")
    cache_dir = None if args.no_cache else Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "shiptally"
    for source in args.source:
        path = Path(source).expanduser()
        if not path.exists():
            raise ValueError("A requested source does not exist: " + source)
        if path.is_file() and not (path.name.endswith(".jsonl") or path.name.endswith(".tar.gz")):
            raise ValueError("Source files must end in .jsonl or .tar.gz.")
    paths = discover(args.source, defaults=not args.no_default_sources)
    entries, diagnostics = load_sources(paths, cache_dir)
    data = build(entries, Mapper(rules), args.since, args.until, args.author, args.github,
        read_prices(args.codex_prices) if args.codex_prices else None, args.all_authors)
    data["diagnostics"] = diagnostics
    if diagnostics["skipped"]:
        data["warnings"].append(str(diagnostics["skipped"]) + " input files could not be read; totals may be incomplete.")
    if data["summary"].get("git_errors", 0):
        data["warnings"].append("Some git history could not be read; affected output counts are unknown.")
    return data
