#!/usr/bin/env python3
"""Packwiz index hashini pack.toml'a yazar ve paket sürümünü artırır."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def finalize(pack_path: Path = Path("pack.toml"), index_path: Path = Path("index.toml")) -> str:
    source = pack_path.read_text("utf-8")
    version_match = re.search(r'(?m)^version = "(\d+)\.(\d+)\.(\d+)"$', source)
    if not version_match:
        raise RuntimeError("pack.toml sürümü bulunamadı.")
    major, minor, patch = map(int, version_match.groups())
    version = f"{major}.{minor}.{patch + 1}"
    index_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
    source = re.sub(r'(?m)^version = "\d+\.\d+\.\d+"$', f'version = "{version}"', source, count=1)
    source = re.sub(r'(?m)^hash = "[a-fA-F0-9]+"$', f'hash = "{index_hash}"', source, count=1)
    pack_path.write_text(source, "utf-8", newline="\n")
    return version


if __name__ == "__main__":
    print(finalize())
