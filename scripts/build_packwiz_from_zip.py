#!/usr/bin/env python3
"""Build Karpuz Packwiz metadata from a local mods ZIP without server credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath


GAME_ROOTS = ("config/", "resourcepacks/")
GAME_FILES = {"options.txt", "servers.dat"}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_entry_name(raw: str) -> str:
    normalized = str(PurePosixPath(raw.replace("\\", "/")))
    if not normalized or normalized == "." or normalized.startswith("../") or "/../" in normalized or normalized.startswith("/"):
        raise ValueError(f"Güvensiz ZIP yolu: {raw}")
    name = PurePosixPath(normalized).name
    if name != normalized:
        raise ValueError(f"Mods ZIP'i yalnızca kökte JAR dosyaları içerebilir: {raw}")
    return name


def hash_zip_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_game_files(repo: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(repo.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file():
            continue
        relative = path.relative_to(repo).as_posix()
        if relative in GAME_FILES or relative.startswith(GAME_ROOTS):
            files.append({"file": relative, "hash": sha256_path(path), "size": path.stat().st_size})
    return files


def render_index(files: list[dict[str, object]]) -> str:
    lines = ['hash-format = "sha256"', ""]
    for entry in files:
        escaped = str(entry["file"]).replace("\\", "\\\\").replace('"', '\\"')
        lines.extend([
            "[[files]]",
            f'file = "{escaped}"',
            f'hash = "{entry["hash"]}"',
            f'size = {entry["size"]}',
            "",
        ])
    return "\n".join(lines)


def update_pack(repo: Path, *, version: str, index_hash: str, manifest_hash: str) -> None:
    path = repo / "pack.toml"
    source = path.read_text(encoding="utf-8")
    source = re.sub(r'(?m)^version\s*=\s*"[^"]*"', f'version = "{version}"', source, count=1)
    source = re.sub(r'(?m)^(hash\s*=\s*)"[a-fA-F0-9]+"', rf'\g<1>"{index_hash}"', source, count=1)
    source = re.sub(r"(?ms)\n\[karpuz\].*?(?=\n\[|\Z)", "", source).rstrip()
    source += (
        "\n\n[karpuz]\n"
        'mods-manifest = "mods-manifest.json"\n'
        'mods-manifest-hash-format = "sha256"\n'
        f'mods-manifest-hash = "{manifest_hash}"\n'
    )
    path.write_text(source, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--url", default="https://mods.karpuz.network/Karpuz-Network-Modpack.zip")
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    zip_path = args.zip.resolve()
    archive_hash = sha256_path(zip_path)
    archive_size = zip_path.stat().st_size
    mods: list[dict[str, object]] = []
    seen_names: set[str] = set()
    seen_hashes: dict[str, str] = {}
    duplicates: list[str] = []

    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not info.filename.lower().endswith(".jar"):
                continue
            name = safe_entry_name(info.filename)
            name_key = name.lower()
            if name_key in seen_names:
                raise ValueError(f"Yinelenen JAR adı: {name}")
            seen_names.add(name_key)
            digest = hash_zip_entry(archive, info)
            if digest in seen_hashes:
                duplicates.append(f"{name} == {seen_hashes[digest]}")
                continue
            seen_hashes[digest] = name
            mods.append({"name": name, "size": info.file_size, "sha256": digest})

    mods.sort(key=lambda item: str(item["name"]).lower())
    manifest = {
        "format": 1,
        "archive": {"url": args.url, "size": archive_size, "sha256": archive_hash},
        "files": mods,
    }
    manifest_path = repo / "mods-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    game_files = collect_game_files(repo)
    game_files.extend({"file": f'mods/{item["name"]}', "hash": item["sha256"], "size": item["size"]} for item in mods)
    game_files.sort(key=lambda item: str(item["file"]).lower())
    index_path = repo / "index.toml"
    index_path.write_text(render_index(game_files), encoding="utf-8", newline="\n")
    update_pack(repo, version=args.version, index_hash=sha256_path(index_path), manifest_hash=sha256_path(manifest_path))

    print(f"Packwiz hazır: {len(mods)} benzersiz mod, {len(game_files) - len(mods)} oyun dosyası")
    for duplicate in duplicates:
        print(f"Atlanan birebir kopya: {duplicate}")


if __name__ == "__main__":
    main()
