#!/usr/bin/env python3
"""Karpuz Pack dogrulama: pack.toml -> index.toml -> mods/*.pw.toml + repo dosyalari.

Bunlari denetler:
  1. pack.toml icindeki index hash'i ile index.toml'un gercek sha256'si eslesir.
  2. index.toml'da yalnizca izinli oyun dosyalari bulunur (config/, resourcepacks/,
     options.txt, servers.dat) ve metafile girdileri mods/*.pw.toml seklindedir.
  3. Her metafile: name/filename/side + [download] url (https) + hash-format + hash tasir;
     yalnizca "url" indirme modu kabul edilir (CurseForge/Modrinth API anahtari launcher'da yoktur).
  4. Metafile hash'i index'teki hash ile, repo dosyasi hash'i de index'teki hash ile eslesir.
  5. Repoda index'te olmayan artık metafile yoktur.
  6. R2 / eski mods-manifest referansi kalmamistir.
"""

from __future__ import annotations

import hashlib
import re
import sys
import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

GAME_ROOTS = ("config/", "resourcepacks/")
GAME_FILES = {"options.txt", "servers.dat"}
SUPPORTED_HASHES = {"md5": 32, "sha1": 40, "sha256": 64, "sha512": 128}
R2_PATTERNS = ("mods.karpuz.network", "Karpuz-Network-Modpack", "mods-manifest")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(value: str) -> str:
    normalized = str(PurePosixPath(str(value).replace("\\", "/")))
    if (not normalized or normalized == "." or normalized.startswith("../")
            or normalized.startswith("/") or "/../" in normalized):
        raise ValueError(f"Guvensiz paket yolu: {value}")
    return normalized


def load_index() -> dict:
    pack = tomllib.loads((ROOT / "pack.toml").read_text(encoding="utf-8"))
    index_path = ROOT / safe_path(pack["index"]["file"])
    actual = sha256(index_path)
    expected = str(pack["index"].get("hash") or "").lower()
    if actual != expected:
        raise ValueError(f"pack.toml ile index.toml sha256 eslesmiyor: {actual} != {expected}")
    return tomllib.loads(index_path.read_text(encoding="utf-8"))


def validate_metafile(rel: str, expected_hash: str) -> dict:
    metafile = ROOT.joinpath(*PurePosixPath(rel).parts)
    if not metafile.is_file():
        raise ValueError(f"Metafile bulunamadi: {rel}")
    if sha256(metafile) != expected_hash:
        raise ValueError(f"Metafile hash'i index ile eslesmiyor: {rel}")

    meta = tomllib.loads(metafile.read_text(encoding="utf-8"))
    name = str(meta.get("name") or "").strip()
    filename = str(meta.get("filename") or "").strip()
    download = meta.get("download") or {}
    url = str(download.get("url") or "").strip()
    hash_format = str(download.get("hash-format") or "").strip().lower()
    hash_value = str(download.get("hash") or "").strip().lower()
    mode = download.get("mode")

    if not name:
        raise ValueError(f"Metafile 'name' alani eksik: {rel}")
    if "/" in filename or "\\" in filename or not filename.lower().endswith(".jar"):
        raise ValueError(f"Gecersiz mod dosya adi: {filename} ({rel})")
    if not url.startswith("https://"):
        raise ValueError(f"Guvenli olmayan indirme adresi: {rel} -> {url}")
    if hash_format not in SUPPORTED_HASHES:
        raise ValueError(f"Desteklenmeyen hash bicimi: {rel} -> {hash_format}")
    if not re.fullmatch(r"[0-9a-f]+", hash_value) or len(hash_value) != SUPPORTED_HASHES[hash_format]:
        raise ValueError(f"Gecersiz hash degeri: {rel}")
    if mode not in (None, "", "url"):
        raise ValueError(f"Yalnizca 'url' indirme modu destekleniyor: {rel} -> {mode}")
    return meta


def check_no_r2_references() -> None:
    for name in ("pack.toml", "index.toml"):
        text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
        for pattern in R2_PATTERNS:
            if pattern in text:
                raise ValueError(f"Eski R2/arsiv referansi bulundu: {name} icinde '{pattern}'")


def main() -> int:
    index = load_index()
    check_no_r2_references()

    files = index.get("files") or []
    if not files:
        raise ValueError("index.toml bos")

    metafiles_in_index: set[str] = set()
    mod_count = 0
    for entry in files:
        rel = safe_path(str(entry["file"]))
        hash_value = str(entry.get("hash") or "").lower()

        if entry.get("metafile") is True:
            if not (rel.startswith("mods/") and rel.endswith(".pw.toml")):
                raise ValueError(f"Metafile yolu gecersiz: {rel}")
            validate_metafile(rel, hash_value)
            metafiles_in_index.add(rel)
            mod_count += 1
            continue

        if rel.startswith("mods/"):
            raise ValueError(f"index.toml dogrudan mod jar'i iceremez (metafile bekleniyor): {rel}")
        if rel not in GAME_FILES and not rel.startswith(GAME_ROOTS):
            raise ValueError(f"Beyaz liste disi index dosyasi: {rel}")
        local = ROOT.joinpath(*PurePosixPath(rel).parts)
        if not local.is_file():
            raise ValueError(f"Yerel paket dosyasi bulunamadi: {rel}")
        if sha256(local) != hash_value:
            hint = ""
            try:
                if b"\r\n" in local.read_bytes():
                    hint = " (CRLF satir sonu tespit edildi, LF bekleniyor)"
            except Exception:  # pragma: no cover
                pass
            raise ValueError(f"Dosya index ile eslesmiyor: {rel}{hint}")

    for metafile in sorted((ROOT / "mods").glob("*.pw.toml")):
        rel = f"mods/{metafile.name}"
        if rel not in metafiles_in_index:
            raise ValueError(f"Index'te olmayan artık metafile: {rel}")

    print(f"Paket dogrulandi: {mod_count} mod, {len(files)} yonetilen dosya")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as error:
        print(f"DOGRULAMA HATASI: {error}", file=sys.stderr)
        sys.exit(1)
