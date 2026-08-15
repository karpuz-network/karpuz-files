#!/usr/bin/env python3
"""Crafty sunucusundaki etkin modları doğrulanmış launcher paketine dönüştürür."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_MODS = 500
CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_crafty_archive(base_url: str, server_id: str, token: str, destination: Path) -> None:
    encoded_path = urllib.parse.quote("mods", safe="")
    url = f"{base_url.rstrip('/')}/api/v2/servers/{server_id}/files/{encoded_path}/download"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": "Karpuz-Pack-Sync/1.0"},
    )
    with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as output:
        content_type = response.headers.get("Content-Type", "")
        if response.status != 200:
            raise RuntimeError(f"Crafty indirme isteği başarısız: HTTP {response.status}")
        if "text/html" in content_type.lower() or "application/json" in content_type.lower():
            raise RuntimeError("Crafty mod arşivi yerine giriş/hata yanıtı döndürdü.")
        copied = 0
        while chunk := response.read(CHUNK_SIZE):
            copied += len(chunk)
            if copied > MAX_ARCHIVE_BYTES:
                raise RuntimeError("Crafty mod arşivi güvenli boyut sınırını aşıyor.")
            output.write(chunk)


def _is_symlink(entry: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((entry.external_attr >> 16) & 0xFFFF)


def prepare_pack(source_zip: Path, output_zip: Path, public_base_url: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="karpuz-mods-") as temp_name:
        extracted = Path(temp_name)
        records: list[dict] = []
        seen: set[str] = set()
        total_size = 0

        with zipfile.ZipFile(source_zip) as archive:
            for entry in archive.infolist():
                if entry.is_dir() or not entry.filename.lower().endswith(".jar"):
                    continue
                if _is_symlink(entry):
                    raise RuntimeError(f"Sembolik bağlantıya izin verilmiyor: {entry.filename}")
                name = Path(entry.filename.replace("\\", "/")).name
                if not name or name in {".", ".."}:
                    raise RuntimeError(f"Geçersiz mod dosyası adı: {entry.filename}")
                key = name.casefold()
                if key in seen:
                    raise RuntimeError(f"Yinelenen mod dosyası adı: {name}")
                if entry.file_size <= 0 or entry.file_size > MAX_FILE_BYTES:
                    raise RuntimeError(f"Geçersiz mod dosyası boyutu: {name}")
                seen.add(key)
                total_size += entry.file_size
                if total_size > MAX_ARCHIVE_BYTES:
                    raise RuntimeError("Açılmış mod dosyaları güvenli boyut sınırını aşıyor.")

                target = extracted / name
                digest = hashlib.sha256()
                size = 0
                with archive.open(entry) as source, target.open("wb") as output:
                    while chunk := source.read(CHUNK_SIZE):
                        size += len(chunk)
                        digest.update(chunk)
                        output.write(chunk)
                if size != entry.file_size:
                    raise RuntimeError(f"Mod dosyası eksik açıldı: {name}")
                records.append({"name": name, "size": size, "sha256": digest.hexdigest()})

        if not records or len(records) > MAX_MODS:
            raise RuntimeError(f"Etkin mod sayısı güvenli aralıkta değil: {len(records)}")

        records.sort(key=lambda item: item["name"].casefold())
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
            for record in records:
                info = zipfile.ZipInfo(record["name"], date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100644 << 16
                with (extracted / record["name"]).open("rb") as source, output.open(info, "w") as target:
                    shutil.copyfileobj(source, target, CHUNK_SIZE)

    archive_hash = sha256_file(output_zip)
    versioned_key = f"Karpuz-Network-Modpack-{archive_hash[:16]}.zip"
    return {
        "format": 1,
        "archive": {
            "url": f"{public_base_url.rstrip('/')}/{versioned_key}",
            "size": output_zip.stat().st_size,
            "sha256": archive_hash,
        },
        "files": records,
    }


def upload_to_r2(archive_path: Path, manifest: dict) -> None:
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError("R2 yüklemesi için boto3 kurulu değil.") from error

    required = ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Eksik R2 ayarı: {', '.join(missing)}")

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET"]
    versioned_key = manifest["archive"]["url"].rsplit("/", 1)[-1]
    immutable = {"ContentType": "application/zip", "CacheControl": "public, max-age=31536000, immutable"}
    latest = {"ContentType": "application/zip", "CacheControl": "public, max-age=300"}
    client.upload_file(str(archive_path), bucket, versioned_key, ExtraArgs=immutable)
    client.upload_file(str(archive_path), bucket, "Karpuz-Network-Modpack.zip", ExtraArgs=latest)


def write_github_output(changed: bool, manifest: dict) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"changed={'true' if changed else 'false'}\n")
        output.write(f"mod_count={len(manifest['files'])}\n")
        output.write(f"archive_sha256={manifest['archive']['sha256']}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", type=Path, help="Crafty yerine yerel arşiv kullan")
    parser.add_argument("--manifest", type=Path, default=Path("mods-manifest.json"))
    parser.add_argument("--public-base-url", default=os.environ.get("R2_PUBLIC_BASE_URL", "https://mods.karpuz.network"))
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="karpuz-sync-") as temp_name:
        temp = Path(temp_name)
        source_zip = args.source_zip or temp / "crafty-mods.zip"
        if args.source_zip is None:
            token = os.environ.get("CRAFTY_API_TOKEN", "")
            if not token:
                raise RuntimeError("CRAFTY_API_TOKEN ayarlanmamış.")
            download_crafty_archive(
                os.environ.get("CRAFTY_BASE_URL", "https://crafty.ogut.su"),
                os.environ.get("CRAFTY_SERVER_ID", "ea66dcd1-c015-43bb-9b0f-8dba936f45b5"),
                token,
                source_zip,
            )

        output_zip = temp / "Karpuz-Network-Modpack.zip"
        manifest = prepare_pack(source_zip, output_zip, args.public_base_url)
        previous = json.loads(args.manifest.read_text("utf-8")) if args.manifest.exists() else None
        changed = previous != manifest
        if changed:
            if not args.no_upload:
                upload_to_r2(output_zip, manifest)
            args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8", newline="\n")
        write_github_output(changed, manifest)
        print(f"Etkin mod: {len(manifest['files'])} | Değişiklik: {'evet' if changed else 'hayır'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
