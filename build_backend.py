# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Small PEP 517 backend so offline installs need no build dependencies."""
import base64
import csv
import hashlib
import io
import tarfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
NAME = "shiptally-0.1.0"
DIST = "shiptally-0.1.0.dist-info"


def metadata():
    return ("Metadata-Version: 2.4\nName: shiptally\nVersion: 0.1.0\n"
            "Summary: Join local AI coding usage to git output, per project.\n"
            "Author: Ninon\nRequires-Python: >=3.9\nLicense-Expression: GPL-3.0-only\n"
            "License-File: LICENSE\nDescription-Content-Type: text/markdown\n"
            "Project-URL: Repository, https://github.com/ninondev/shiptally\n\n"
            + (ROOT / "README.md").read_text(encoding="utf-8"))


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_sdist(config_settings=None):
    return []


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = "shiptally-0.1.0-py3-none-any.whl"
    files = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sorted((ROOT / "shiptally").glob("*.py"))}
    files[DIST + "/METADATA"] = metadata().encode()
    files[DIST + "/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: shiptally\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    files[DIST + "/entry_points.txt"] = b"[console_scripts]\nshiptally = shiptally.cli:main\n"
    files[DIST + "/licenses/LICENSE"] = (ROOT / "LICENSE").read_bytes()
    records = io.StringIO(newline="")
    writer = csv.writer(records)
    for path, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([path, "sha256=" + digest, len(data)])
    writer.writerow([DIST + "/RECORD", "", ""])
    files[DIST + "/RECORD"] = records.getvalue().encode()
    with ZipFile(Path(wheel_directory) / name, "w", ZIP_DEFLATED) as wheel:
        for path, data in files.items():
            wheel.writestr(path, data)
    return name


def build_sdist(sdist_directory, config_settings=None):
    name = NAME + ".tar.gz"
    with tarfile.open(Path(sdist_directory) / name, "w:gz") as archive:
        for path in sorted(ROOT.rglob("*")):
            rel = path.relative_to(ROOT)
            if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                continue
            if path.is_file() and path.suffix not in (".pyc", ".whl", ".gz"):
                archive.add(path, arcname=NAME + "/" + rel.as_posix())
        payload = metadata().encode()
        entry = tarfile.TarInfo(NAME + "/PKG-INFO")
        entry.size = len(payload)
        archive.addfile(entry, io.BytesIO(payload))
    return name
