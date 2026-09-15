#!/usr/bin/env python3
"""Validate Karpuz Packwiz metadata without downloading the large mod archive."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(value: str) -> str:
    normalized = str(PurePosixPath(value.replace("\\", "/")))
    if not normalized or normalized == "." or normalized.startswith("../") or normalized.startswith("/") or "/../" in normalized:
        raise ValueError(f"Güvensiz paket yolu: {value}")
    return normalized


def main() -> None:
    pack = tomllib.loads((ROOT / "pack.toml").read_text(encoding="utf-8"))
    index_path = ROOT / safe_path(pack["index"]["file"])
    manifest_path = ROOT / safe_path(pack["karpuz"]["mods-manifest"])
    if sha256(index_path) != pack["index"]["hash"]:
        raise ValueError("pack.toml ile index.toml SHA-256 değeri eşleşmiyor")
    if sha256(manifest_path) != pack["karpuz"]["mods-manifest-hash"]:
        raise ValueError("pack.toml ile mods-manifest.json SHA-256 değeri eşleşmiyor")

    index = tomllib.loads(index_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != 1:
        raise ValueError("Desteklenmeyen mod manifest biçimi")
    archive = manifest.get("archive", {})
    if not str(archive.get("url", "")).startswith("https://") or len(str(archive.get("sha256", ""))) != 64 or int(archive.get("size", 0)) <= 0:
        raise ValueError("Arşiv bütünlük bilgileri geçersiz")

    mods: dict[str, dict[str, object]] = {}
    for item in manifest.get("files", []):
        name = safe_path(str(item["name"]))
        if "/" in name or not name.lower().endswith(".jar"):
            raise ValueError(f"Geçersiz mod adı: {name}")
        key = name.lower()
        if key in mods:
            raise ValueError(f"Yinelenen mod adı: {name}")
        mods[key] = item

    indexed_mods: set[str] = set()
    for item in index.get("files", []):
        relative = safe_path(str(item["file"]))
        expected_hash = str(item["hash"]).lower()
        expected_size = int(item["size"])
        if relative.startswith("mods/"):
            name = PurePosixPath(relative).name
            mod = mods.get(name.lower())
            if not mod or mod["sha256"] != expected_hash or int(mod["size"]) != expected_size:
                raise ValueError(f"Index ve mod manifesti eşleşmiyor: {relative}")
            indexed_mods.add(name.lower())
            continue
        if relative not in {"options.txt", "servers.dat"} and not relative.startswith(("config/", "resourcepacks/")):
            raise ValueError(f"Oyun dışı index dosyası: {relative}")
        local = ROOT.joinpath(*PurePosixPath(relative).parts)
        if not local.is_file() or local.stat().st_size != expected_size or sha256(local) != expected_hash:
            raise ValueError(f"Yerel paket dosyası index ile eşleşmiyor: {relative}")

    if indexed_mods != set(mods):
        raise ValueError("Index ve mod manifestindeki mod listeleri farklı")
    print(f"Paket doğrulandı: {len(mods)} benzersiz mod, {len(index.get('files', []))} yönetilen dosya")


if __name__ == "__main__":
    main()
