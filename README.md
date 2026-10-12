# shiptally

See what your AI coding tokens produced, per project.

shiptally reads your local Claude Code and Codex logs and joins that usage to
git commits and line changes. Other tools are not supported yet. You can also
ask for public GitHub status and stars.

Try the packaged synthetic report without reading any logs:

```sh
shiptally --demo
shiptally --demo --html demo.html
```

This is the real output of `shiptally --demo`. All of its data is made up:

```text
Spent $428.77 (list price) over 60 days -> 402 commits in 7 repos, run with --github to count public repos and stars
Synthetic demo data.
Commit authors: Synthetic author; precomputed git statistics

Project                                   List $  Claude out  Codex out  Sessions  Days             First–last  Commits       Lines +/-  Public ★
----------------------------------------  ------  ----------  ---------  --------  ----  ---------------------  -------  --------------  --------
~/Projects/build-dashboard (2 folders)    157.96   3,210,086  2,317,798       161    48  2026-08-01–2026-09-29       74  +19,630/-8,240     no ★?
~/Projects/menu-bar-clock (2 folders)     103.15   2,153,899  1,595,496       171    60  2026-08-01–2026-09-29       86  +12,840/-4,930     no ★?
~/Projects/research-notebook (2 folders)   64.69   1,316,911  1,009,812        88    36  2026-08-01–2026-09-29       19   +6,120/-2,470     no ★?
~/Projects/archive-cli (2 folders)         47.16   1,044,968    527,496        91    44  2026-08-01–2026-09-29       63   +7,240/-2,110     no ★?
~/Projects/abandoned-search (2 folders)    32.19     719,870    465,757        23     8  2026-08-01–2026-08-18        0           +0/-0     no ★?
~/Projects/garden-game-mod (2 folders)     22.28     449,368    243,196        45    22  2026-08-01–2026-09-24       28   +4,830/-1,670     no ★?
~/Projects/tiny-sequence-lib (2 folders)    1.33      25,929     19,288        26    18  2026-08-01–2026-09-29      132     +2,380/-910     no ★?

List-price equivalent, not a bill. Subscriptions differ.
Codex: tokens only; no prices supplied.
? = not checked or unavailable. Dates use UTC.
```

Screenshots of the demo report: `docs/screenshot-light.png` and
`docs/screenshot-dark.png` (WebKit, 1,280 CSS px).

## Install

Use Python 3.9 or later. No other Python packages are needed.

```sh
pip install .
# Or run without a permanent install:
uvx --from . shiptally --help
```

## Use

```sh
shiptally
shiptally --since 2026-09-01 --until 2026-09-30
shiptally --author 'Your Name' --json
shiptally --all-authors
shiptally --verbose
shiptally --html report.html --lang en
shiptally --html report.html --lang zh --redact
shiptally --github
```

`--github` allows network access. All other commands work offline.

Each project shows its repository root, with the home prefix shortened to `~`.
The project name appears after the path only when it differs from the path's
last component. Home sessions read `~ (home folder)`.
Multiple working directories appear as `N folders`. Text lists them only with
`--verbose`; HTML keeps them in a closed folder disclosure. Long names use an
ellipsis. The text table stays within 160 columns. The HTML table uses ten fixed
columns within a 1,280 CSS px page, with horizontal scrolling on smaller screens.

A supplied source adds to the default log folders. Repeat it to combine sources.
Use `--no-default-sources` to read only supplied sources.
An archive is read as a stream. Files are never unpacked onto disk.

```sh
shiptally --no-default-sources --source ./logs --source ./old-logs.tar.gz --no-cache
```

## Synthetic example

`--demo` generates synthetic usage inside the Python package with a fixed seed
of `73060`. It covers 60 days, from 2026-08-01 through 2026-09-29, for one
fictional heavy user across seven made-up projects: a menu-bar clock, an archive
CLI, a build dashboard, a garden game mod, an abandoned search experiment,
a small sequence library and a research notebook.

Session counts and output tokens vary by project and day. Claude equivalents
use generated input, output, cache-read and cache-write counts with the packaged
price snapshot. Codex remains tokens only. Git commits and line counts are
precomputed fictional statistics in `shiptally/demo.py`; no repositories are
created or scanned at demo time. The abandoned experiment has spend and zero
commits. The library has little agent usage and many commits. These examples
illustrate different patterns of work; commits do not establish AI causation.

Text and HTML always display `Synthetic demo data`, including Chinese and
redacted reports. JSON includes `"demo_label": "Synthetic demo data"`, the seed
and the git-statistics method. The demo skips logs, user config, cache, git scans
and network requests. It supports text, JSON, HTML, language, verbose and
redaction options. Input, date, pricing, author and GitHub options cannot be
combined with this fixed sample.

```sh
shiptally --demo
# Write the offline HTML to your chosen path, without installing the package:
scripts/render-demo.sh ./demo.html
# Regenerate the bundled preview for screenshots in light and dark mode:
scripts/render-demo.sh docs/demo.html
```

For parser and git experiments, the optional fixture generator creates fake
logs and throwaway repositories. Choose a new folder that does not exist:

```sh
python3 docs/make_demo.py ./demo-data
shiptally --no-default-sources --source ./demo-data/logs --config ./demo-data/config.toml --no-cache
```

## What is counted

Claude dollars are a USD **list-price equivalent**, not a bill. Subscriptions
differ. The embedded table includes input, output, cache reads and both cache
write rates. It applies the Haiku 5.5 prompt tiers from the copied table.
The table was copied from a local snapshot on 2026-10-08. It was not checked
online. Its source is https://platform.claude.com/docs/en/about-claude/pricing.
An unknown Claude model uses the Opus 5.5 fallback and adds a warning.

Claude usage takes the last iteration. A message id is counted once across
files. The record with the most output tokens wins. A tie uses the oldest file.
Subagent files belong to the parent session.

Codex counts output tokens without a dollar price. Response ids are counted
once across files. If a file has no direct usage records, the first cumulative
event uses its last usage. Later events use the change in the cumulative total.
A repeated total adds nothing. A reset uses the last usage. Matching archive
members are skipped when a live file is present.

You can supply Codex rates in USD per million tokens:

```json
{"input": 2, "cached_input": 0.5, "output": 8}
```

Save that as `prices.json`, then use `shiptally --codex-prices prices.json`.
Cached input is part of total input. Supplied Codex costs join the list-price total.

A session belongs to the repository with the most working-directory records.
Worktrees join the main repository through the common git directory. A missing
path containing `/.claude/worktrees/` joins the nearest existing ancestor that
belongs to a git repository. Other missing paths, including sibling `repo-wt`
folders, use the basename fallback. The home folder is named `~ (home folder)`.
Sessions and active days count sessions with usage in the selected window.
Dates use UTC. Both date limits include the whole day. Without date limits,
the git window runs from the first to the last included usage day.

Git commits include all local branches. By default, only commits whose author
email exactly equals the repository's effective `git config user.email` count.
Repository config overrides global config. If no email is configured, that
repository contributes no commits or lines and a warning explains how to fix it.
`--all-authors` counts every author. `--author PATTERN` uses git's author regular
expression instead. Those two options are mutually exclusive. Every summary
prints the author rule used.
Shared worktrees are counted once. Line counts come from git numstat. Binary
files and merge resolutions without a patch add no lines. A commit may include
work done without an agent.

A GitHub remote does not prove a repository is public. Public status and stars
stay unknown until `--github` checks them. The command uses `gh api` if it is
available, or the public REST API. Each request has a 10-second timeout.
A failed check stays unknown.

## Privacy

The app never stores or prints message text. It reads usage fields, ids,
timestamps and working directories. The cache holds these counts and metadata,
plus file paths, sizes and modification times. It also keeps model names for
price calculations. It does not hold prompts, replies or tool output.

The default cache is `~/.cache/shiptally/`. `XDG_CACHE_HOME` can change its base.
Writes replace each cache file atomically. `--no-cache` reads and writes no cache.
Unchanged files are loaded from cache. The first parse uses at most four workers.

JSON includes project paths and remote names by default; the home path prefix
is always printed as `~`, including diagnostics. `--redact` replaces
names, paths and remote names with stable hash labels. It hides error details.
Dates and counts remain. Check a report before sharing it: these facts can still
help someone identify a project. The HTML file has no external resources and
makes no network requests when opened.

The default log folders are:

- `$CLAUDE_CONFIG_DIR/projects`, or `~/.claude/projects`.
- `$CODEX_HOME/sessions` and `$CODEX_HOME/archived_sessions`, or their folders under `~/.codex`.

## Project config

The default file is `~/.config/shiptally/config.toml`. `XDG_CONFIG_HOME` can
change its base. `--config` selects another file.

```toml
[[projects]]
match = ["old-name"]
name = "New name"

[[projects]]
match = ["repo-a", "repo-b"]
merge = "shared-project"
name = "Shared project"

[[projects]]
match = ["private-project"]
hide = true
```

A match is an exact project name or path. Rules run in order. Hidden projects
are left out of totals. Merged projects keep all their repository paths.
For Python 3.9 support, the config accepts a small TOML subset: `[[projects]]`,
one-line quoted strings, string lists and booleans. Other TOML forms give an error.

## Options

| Option | Use |
| --- | --- |
| `--source PATH` | Add a JSONL file, log folder or `.tar.gz`; repeat to combine |
| `--no-default-sources` | Skip default log folders |
| `--since DATE`, `--until DATE` | Included UTC dates, in `YYYY-MM-DD` form |
| `--author PATTERN` | Git author regular expression |
| `--all-authors` | Count every author instead of the default exact email match |
| `--verbose` | List working directories below the text table |
| `--demo` | Render packaged synthetic data without reading local inputs |
| `--config FILE` | Rename, merge or hide projects |
| `--codex-prices JSON` | Your Codex rates per million tokens |
| `--github` | Allow GitHub network requests |
| `--html FILE` | Write one offline report |
| `--json` | Print schema version 1 JSON |
| `--lang en\|zh` | UI language; default `en` |
| `--redact` | Stable labels for names, paths and remotes |
| `--no-cache` | Parse without cache reads or writes |

## Limits

Only Claude Code and Codex are supported for now. Log formats can change.
Malformed records are skipped. Unreadable files are counted in diagnostics and add a warning.
A failed git history read shows unknown counts; a confirmed empty repository shows zero.
Files without usage events do not add sessions or active days.

Without response ids, the same Codex history in different files can be counted
twice. A file that mixes direct records and cumulative records uses only the
direct records. Missing repositories have no git output. Separate clones of
a repository have separate git histories and can count the same commits twice.
Stars describe the current repository, not the selected time window.
List prices can change. Commits and lines are not a measure of value, quality,
or the work caused by AI. A warm-cache run still reads git history.
Browser layout at 1,280 CSS px is captured in the bundled screenshots; current
HTML checks cover markup and fixed-column styles.

## Contribute and license

See [CONTRIBUTING.md](CONTRIBUTING.md).

Copyright (c) 2026 Ninon. Licensed under MIT. See [LICENSE](LICENSE).

If this was useful to you, a star helps other people find it.
