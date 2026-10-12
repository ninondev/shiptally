#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
set -eu
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 OUTPUT.html" >&2
    exit 2
fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" -c '
import sys
sys.path.insert(0, sys.argv.pop(1))
from shiptally.cli import main
sys.exit(main(["--demo", "--html", sys.argv[1]]))
' "$script_dir/.." "$1"
