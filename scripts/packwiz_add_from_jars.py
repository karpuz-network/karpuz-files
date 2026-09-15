#!/usr/bin/env python3
"""Karpuz Pack: yerel mod JAR'larindan packwiz metafile'lari (mods/*.pw.toml) uretir.

Her mod icin resmi indirme linki + hash iceren packwiz metadatasi yazilir:
  * Modrinth  : sha512 ile /v2/version_files uzerinden birebir dosya eslesmesi (indirme gerekmez)
  * CurseForge: fingerprint (/v1/fingerprints/matches) -> file id -> resmi CDN download url
  * Ozel modlar: scripts/private-mods.json icindeki esleme (GitHub Release asset vb.)

Ardindan `packwiz refresh` cagrilir; index.toml ve pack.toml index hash'i packwiz tarafindan uretilir.

Kullanim:
  py scripts/packwiz_add_from_jars.py --report-only
  py scripts/packwiz_add_from_jars.py
  py scripts/packwiz_add_from_jars.py --cf-key <KEY> --accept-cf-mismatch

CurseForge anahtari CF_API_KEY ortam degiskeninden de okunur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

MODRINTH_API = "https://api.modrinth.com/v2"
CURSEFORGE_API = "https://api.curseforge.com/v1"
USER_AGENT = "KarpuzNetwork-PackBuilder/1.0 (+https://karpuz.network)"

SUPPORTED_HASHES = ("sha512", "sha256", "sha1")


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def http_json(url: str, *, method: str = "GET", body: object = None,
              headers: dict[str, str] | None = None, retries: int = 4,
              timeout: int = 60):
    """JSON donduren HTTP istegi; 429/5xx durumunda bekleyip yeniden dener."""
    payload = None
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)

    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            detail = ""
            try:
                detail = error.read().decode("utf-8", "replace")[:300]
            except Exception:  # pragma: no cover - tani amacli
                pass
            raise RuntimeError(f"HTTP {error.code} {url} {detail}") from error
        except Exception as error:  # ag hatasi
            last_error = error
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
    raise RuntimeError(f"Istek basarisiz: {url} ({last_error})")


def http_download(url: str, destination: Path, *, retries: int = 4) -> None:
    """Dosyayi diske indirir (dogrulama icin)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as stream:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
            return
        except Exception as error:
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Indirme basarisiz: {url} ({last_error})")


# --------------------------------------------------------------------------- #
# Hash yardimcilari
# --------------------------------------------------------------------------- #

def hash_path(path: Path, algorithms: tuple[str, ...] = SUPPORTED_HASHES) -> dict[str, str]:
    """Dosyayi tek gecisste okurken istenen tum hash'leri hesaplar."""
    digests = {name: hashlib.new(name) for name in algorithms}
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            for digest in digests.values():
                digest.update(chunk)
    return {name: digest.hexdigest() for name, digest in digests.items()}


def murmur2_32(data: bytes, seed: int = 1) -> int:
    """MurmurHash2 (32-bit, little endian) - go-murmur ile ayni sonucu verir."""
    length = len(data)
    multiplier = 0x5BD1E995
    shift = 24
    hash_value = (seed ^ length) & 0xFFFFFFFF

    index = 0
    limit = length - (length % 4)
    while index < limit:
        k = data[index] | (data[index + 1] << 8) | (data[index + 2] << 16) | (data[index + 3] << 24)
        k = (k * multiplier) & 0xFFFFFFFF
        k ^= k >> shift
        k = (k * multiplier) & 0xFFFFFFFF
        hash_value = (hash_value * multiplier) & 0xFFFFFFFF
        hash_value ^= k
        index += 4

    remainder = length & 3
    if remainder == 3:
        hash_value ^= data[index + 2] << 16
    if remainder >= 2:
        hash_value ^= data[index + 1] << 8
    if remainder >= 1:
        hash_value ^= data[index]
        hash_value = (hash_value * multiplier) & 0xFFFFFFFF

    hash_value ^= hash_value >> 13
    hash_value = (hash_value * multiplier) & 0xFFFFFFFF
    hash_value ^= hash_value >> 15
    return hash_value & 0xFFFFFFFF


def curseforge_fingerprint(path: Path) -> int:
    """CurseForge fingerprint: bosluk baytlari (9/10/13/32) atilip murmur2(seed=1)."""
    raw = path.read_bytes().translate(None, b"\t\n\r ")
    return murmur2_32(raw, 1)


# --------------------------------------------------------------------------- #
# TOML / metafile
# --------------------------------------------------------------------------- #

def toml_string(value: str) -> str:
    """TOML basic string olarak guvenli sekilde kacislar."""
    escaped = (value.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return f'"{escaped}"'


def slugify(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"\(.*\)", "", lowered)
    lowered = re.sub(r" - .+", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered or "mod"


def render_metafile(*, name: str, filename: str, url: str, hash_format: str,
                    hash_value: str, side: str = "both") -> str:
    """packwiz'in urettigi bicimle ayni metafile (girinti yok, url modu)."""
    return (
        f"name = {toml_string(name)}\n"
        f"filename = {toml_string(filename)}\n"
        f"side = {toml_string(side)}\n"
        "\n"
        "[download]\n"
        f"url = {toml_string(url)}\n"
        f"hash-format = {toml_string(hash_format)}\n"
        f"hash = {toml_string(hash_value)}\n"
    )


def safe_relative(value: str) -> str:
    normalized = str(PurePosixPath(value.replace("\\", "/")))
    if (not normalized or normalized == "." or normalized.startswith("../")
            or normalized.startswith("/") or "/../" in normalized):
        raise ValueError(f"Guvensiz yol: {value}")
    return normalized


def load_pack(repo: Path) -> dict:
    return tomllib.loads((repo / "pack.toml").read_text(encoding="utf-8"))


def indexed_mod_names(repo: Path) -> list[str]:
    """index.toml'daki pakete dahil mod dosya adlarini dondurur."""
    pack = load_pack(repo)
    index_path = repo / safe_relative(pack["index"]["file"])
    index = tomllib.loads(index_path.read_text(encoding="utf-8"))
    names = []
    for entry in index.get("files", []):
        path = safe_relative(str(entry["file"]))
        if path.startswith("mods/") and not path.endswith(".pw.toml"):
            names.append(PurePosixPath(path).name)
    return names


# --------------------------------------------------------------------------- #
# Modrinth
# --------------------------------------------------------------------------- #

def chunks(items, size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def modrinth_versions_by_hash(hashes: list[str], algorithm: str) -> dict[str, dict]:
    """hash -> Modrinth surum nesnesi (birebir dosya eslesmesi)."""
    found: dict[str, dict] = {}
    for batch in chunks(hashes, 100):
        response = http_json(
            f"{MODRINTH_API}/version_files",
            method="POST",
            body={"hashes": batch, "algorithm": algorithm},
        )
        if isinstance(response, dict):
            found.update(response)
    return found


def modrinth_project_index(project_ids: list[str]) -> dict[str, dict]:
    """project_id -> {"slug": ..., "title": ...} (GET /v2/projects?ids=[...])"""
    index: dict[str, dict] = {}
    for batch in chunks(sorted(set(project_ids)), 100):
        query = urllib.parse.quote(json.dumps(batch, separators=(",", ":")))
        response = http_json(f"{MODRINTH_API}/projects?ids={query}")
        for project in response or []:
            index[str(project.get("id"))] = {
                "slug": str(project.get("slug") or ""),
                "title": str(project.get("title") or ""),
            }
    return index


def pick_modrinth_file(version: dict, algorithm: str) -> dict | None:
    files = version.get("files") or []
    primary = next((item for item in files if item.get("primary")), None)
    for candidate in [primary, *files]:
        if not candidate:
            continue
        digest = (candidate.get("hashes") or {}).get(algorithm)
        if digest and candidate.get("url"):
            return {
                "url": str(candidate["url"]),
                "filename": str(candidate.get("filename") or ""),
                "size": candidate.get("size"),
                "hash": str(digest).lower(),
            }
    return None


# --------------------------------------------------------------------------- #
# CurseForge
# --------------------------------------------------------------------------- #

def curseforge_fingerprint_matches(fingerprints: list[int], api_key: str) -> dict[str, dict]:
    """fingerprint -> {"fileId": int, "file": {...}} (birebir eslesenler)."""
    matches: dict[str, dict] = {}
    for batch in chunks(fingerprints, 100):
        response = http_json(
            f"{CURSEFORGE_API}/fingerprints",
            method="POST",
            headers={"x-api-key": api_key},
            body={"fingerprints": batch},
        )
        data = (response or {}).get("data") or {}
        for entry in data.get("exactMatches") or []:
            file_info = entry.get("file") or {}
            fingerprint = file_info.get("fileFingerprint")
            if fingerprint is None:
                continue
            matches[str(int(fingerprint))] = {"fileId": int(file_info.get("id") or 0), "file": file_info}
    return matches


def curseforge_cdn_url(file_id: int, file_name: str) -> str:
    """API indirmesi kapali dosyalar icin resmi CurseForge CDN adresi (files/<id//1000>/<id%1000>/<ad>)."""
    return f"https://mediafilez.forgecdn.net/files/{file_id // 1000}/{file_id % 1000}/{urllib.parse.quote(file_name)}"


def curseforge_file_by_fingerprint(fingerprint: int, api_key: str) -> dict | None:
    """Tek fingerprint icin dosya bilgisi (toplu yanitta fingerprint alani yoksa yedek yol)."""
    try:
        response = http_json(
            f"{CURSEFORGE_API}/fingerprints/{fingerprint}?gameId=432",
            method="POST",
            headers={"x-api-key": api_key},
            body={},
        )
    except RuntimeError:
        return None
    data = (response or {}).get("data") or {}
    for entry in data.get("exactMatches") or []:
        file_info = entry.get("file") or {}
        return {"fileId": int(entry.get("id") or file_info.get("id") or 0), "file": file_info}
    return None


def curseforge_download_url(mod_id: int, file_id: int, api_key: str) -> str | None:
    try:
        response = http_json(
            f"{CURSEFORGE_API}/mods/{mod_id}/files/{file_id}/download-url",
            headers={"x-api-key": api_key},
        )
    except RuntimeError:
        return None
    url = (response or {}).get("data")
    return str(url) if url else None


def curseforge_mods(mod_ids: list[int], api_key: str) -> dict[int, dict]:
    index: dict[int, dict] = {}
    for batch in chunks(sorted(set(mod_ids)), 100):
        response = http_json(
            f"{CURSEFORGE_API}/mods",
            method="POST",
            headers={"x-api-key": api_key},
            body={"modIds": batch},
        )
        for mod in (response or {}).get("data") or []:
            index[int(mod.get("id"))] = {
                "name": str(mod.get("name") or ""),
                "slug": str(mod.get("slug") or ""),
            }
    return index


# --------------------------------------------------------------------------- #
# Ozel mod eslemesi + indirme dogrulamasi
# --------------------------------------------------------------------------- #

def load_private_map(path: Path) -> dict[str, dict]:
    """scripts/private-mods.json -> {jar dosya adi: {"name", "url", "slug"}}"""
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    mods = data.get("mods") if isinstance(data, dict) else None
    return {str(key): value for key, value in (mods or {}).items()}


def verify_url(url: str, cache_dir: Path, log) -> dict:
    """Resmi linki indirir, gercek sha256 + boyut dondurur."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]}.jar"
    log(f"    indiriliyor: {url}")
    http_download(url, target)
    digests = hash_path(target, ("sha256",))
    return {"path": target, "sha256": digests["sha256"], "size": target.stat().st_size}


def unique_slug(base: str, taken: set[str]) -> str:
    slug = base or "mod"
    if slug not in taken:
        taken.add(slug)
        return slug
    index = 2
    while f"{slug}-{index}" in taken:
        index += 1
    taken.add(f"{slug}-{index}")
    return f"{slug}-{index}"


# --------------------------------------------------------------------------- #
# Cozumleme
# --------------------------------------------------------------------------- #

def resolve_modrinth(*, jars: list[str], digests: dict[str, dict], log) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    log("Modrinth uzerinde sha512 ile eslesme araniyor...")
    by_sha512 = {digests[name]["sha512"]: name for name in jars}
    matched: dict[str, tuple[dict, str, str]] = {}
    for digest, version in modrinth_versions_by_hash(list(by_sha512), "sha512").items():
        name = by_sha512.get(str(digest).lower())
        if name and isinstance(version, dict):
            matched[name] = (version, "sha512", str(digest).lower())

    leftover = [name for name in jars if name not in matched]
    if leftover:
        log(f"Modrinth sha1 ile tekrar deneniyor ({len(leftover)} jar)...")
        by_sha1 = {digests[name]["sha1"]: name for name in leftover}
        for digest, version in modrinth_versions_by_hash(list(by_sha1), "sha1").items():
            name = by_sha1.get(str(digest).lower())
            if name and isinstance(version, dict):
                matched[name] = (version, "sha1", str(digest).lower())

    projects = modrinth_project_index([str(version.get("project_id"))
                                       for version, _, _ in matched.values()])
    for name, (version, algorithm, digest) in matched.items():
        file_info = pick_modrinth_file(version, algorithm)
        if not file_info:
            continue
        project = projects.get(str(version.get("project_id")), {})
        title = project.get("title") or str(version.get("name") or Path(name).stem)
        entries[name] = {
            "source": "modrinth",
            "slugSource": project.get("slug") or title,
            "name": title,
            "url": file_info["url"],
            "hashFormat": algorithm,
            "hash": file_info["hash"] or digest,
            "size": file_info.get("size"),
            "verified": file_info["hash"] == digest,
            "contentMismatch": False,
        }
    return entries


def resolve_curseforge(*, repo: Path, jars: list[str], digests: dict[str, dict], api_key: str,
                       verify_downloads: bool, cache_dir: Path, log,
                       cdn_fallback: bool = False) -> tuple[dict[str, dict], dict[str, str]]:
    """Fingerprint -> CurseForge file -> resmi CDN indirme linki."""
    entries: dict[str, dict] = {}
    unresolved: dict[str, str] = {}
    log(f"CurseForge fingerprint eslesmesi ({len(jars)} jar)...")

    fingerprints: dict[str, int] = {}
    for name in jars:
        fingerprints[name] = curseforge_fingerprint(repo / "mods" / name)

    matches = curseforge_fingerprint_matches(list(fingerprints.values()), api_key)
    by_fingerprint = {str(value): key for key, value in fingerprints.items()}
    hits: dict[str, dict] = {}
    for fingerprint, match in matches.items():
        name = by_fingerprint.get(str(fingerprint))
        if name:
            hits[name] = match

    mod_ids = [int(match["file"].get("modId") or 0) for match in hits.values()]
    mod_index = curseforge_mods(mod_ids, api_key) if mod_ids else {}

    for name, match in hits.items():
        file_info = match["file"]
        mod_id = int(file_info.get("modId") or 0)
        url = str(file_info.get("downloadUrl") or "")
        if not url:
            url = curseforge_download_url(mod_id, match["fileId"], api_key) or ""
        if not url and cdn_fallback:
            url = curseforge_cdn_url(match["fileId"], str(file_info.get("fileName") or name))
            log(f"    API indirmesi kapali, resmi CDN adresi kullaniliyor: {name}")
        if not url:
            unresolved[name] = "curseforge-indirme-linki-yok (yazar ucuncu taraf indirmeyi kapatmis)"
            continue

        meta = mod_index.get(mod_id, {})
        title = meta.get("name") or Path(name).stem
        record = {
            "source": "curseforge",
            "slugSource": meta.get("slug") or title,
            "name": title,
            "url": url,
            "fileId": match["fileId"],
            "modId": mod_id,
            "hashFormat": "sha256",
            "hash": digests[name]["sha256"],
            "size": digests[name].get("size"),
            "verified": False,
            "contentMismatch": False,
        }
        if verify_downloads:
            downloaded = verify_url(url, cache_dir, log)
            record["hash"] = downloaded["sha256"]
            record["size"] = downloaded["size"]
            record["verified"] = downloaded["sha256"] == digests[name]["sha256"]
            record["contentMismatch"] = not record["verified"]
        entries[name] = record
    return entries, unresolved


def resolve_private(*, jars: list[str], digests: dict[str, dict], private_map: dict[str, dict],
                    verify_downloads: bool, cache_dir: Path, log) -> tuple[dict[str, dict], dict[str, str]]:
    """private-mods.json eslemesi (GitHub Release asset vb.)."""
    entries: dict[str, dict] = {}
    unresolved: dict[str, str] = {}
    for name in jars:
        mapping = private_map.get(name)
        if not mapping:
            continue
        url = str(mapping.get("url") or "")
        if not url.startswith("https://"):
            unresolved[name] = "ozel-mod-https-linki-gecersiz"
            continue
        title = str(mapping.get("name") or Path(name).stem)
        record = {
            "source": "private",
            "slugSource": mapping.get("slug") or title,
            "name": title,
            "url": url,
            "hashFormat": "sha256",
            "hash": digests[name]["sha256"],
            "size": digests[name].get("size"),
            "verified": False,
            "contentMismatch": False,
        }
        if verify_downloads:
            try:
                downloaded = verify_url(url, cache_dir, log)
            except RuntimeError as error:
                record["note"] = f"indirme dogrulanamadi: {error}"
                log(f"    ! {name} indirilemedi (dosya henuz yayinda olmayabilir)")
                entries[name] = record
                continue
            record["hash"] = downloaded["sha256"]
            record["size"] = downloaded["size"]
            record["verified"] = downloaded["sha256"] == digests[name]["sha256"]
            record["contentMismatch"] = not record["verified"]
        entries[name] = record
    return entries, unresolved
# --------------------------------------------------------------------------- #
# Metafile yazimi / refresh
# --------------------------------------------------------------------------- #

def write_metafiles(*, repo: Path, entries: dict[str, dict], log) -> tuple[list[dict], list[dict]]:
    """mods/*.pw.toml dosyalarini yazar; eski/bayat metafile'lari temizler."""
    mods_dir = repo / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)

    taken: set[str] = set()
    written: list[dict] = []
    mismatched: list[dict] = []
    for jar_name in sorted(entries, key=str.lower):
        record = entries[jar_name]
        if record.get("contentMismatch") and not record.get("accepted"):
            mismatched.append({"jar": jar_name, **record})
            continue
        slug = unique_slug(slugify(str(record.get("slugSource") or record.get("name"))), taken)
        meta_name = f"{slug}.pw.toml"
        record["metaFile"] = meta_name
        (mods_dir / meta_name).write_text(
            render_metafile(
                name=str(record["name"]),
                filename=jar_name,
                url=str(record["url"]),
                hash_format=str(record["hashFormat"]),
                hash_value=str(record["hash"]),
            ),
            encoding="utf-8", newline="\n")
        written.append({
            "jar": jar_name, "metaFile": f"mods/{meta_name}", "source": record["source"],
            "name": record["name"], "url": record["url"], "hash-format": record["hashFormat"],
            "hash": record["hash"], "verified": bool(record.get("verified")),
        })

    managed = {entry["metaFile"].split("/", 1)[1] for entry in written}
    for existing in sorted(mods_dir.glob("*.pw.toml")):
        if existing.name not in managed:
            log(f"  bayat metafile silindi: mods/{existing.name}")
            existing.unlink()
    return written, mismatched


def run_packwiz_refresh(repo: Path, log) -> None:
    executable = shutil.which("packwiz")
    if not executable:
        raise RuntimeError("packwiz bulunamadi. Kurulum: go install github.com/packwiz/packwiz@latest")
    log("packwiz refresh calistiriliyor...")
    result = subprocess.run([executable, "refresh"], cwd=repo, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(f"packwiz refresh basarisiz:\n{output.strip()}")
    log("  index.toml ve pack.toml guncellendi")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Yerel mod JAR'larindan packwiz metafile'lari uretir")
    parser.add_argument("--repo", default=None, help="karpuz-files kok dizini (varsayilan: betigin ust dizini)")
    parser.add_argument("--cf-key", default=None, help="CurseForge API anahtari (varsayilan: CF_API_KEY)")
    parser.add_argument("--private", default=None, help="Ozel mod eslemesi (varsayilan: scripts/private-mods.json)")
    parser.add_argument("--report", default=None, help="Cozumleme raporu (varsayilan: resolution-report.json)")
    parser.add_argument("--cache", default=None, help="Dogrulama onbellegi (varsayilan: .packwiz-verify-cache)")
    parser.add_argument("--report-only", action="store_true", help="Hicbir dosya yazmadan sadece ozet uret")
    parser.add_argument("--no-verify-downloads", action="store_true",
                        help="Resmi linkleri indirip hash dogrulamasi yapma (hizli ama dogrulamasiz)")
    parser.add_argument("--accept-cf-mismatch", action="store_true",
                        help="CurseForge dosyasi yerel jar ile ayni degilse de kabul et")
    parser.add_argument("--cf-cdn-fallback", action="store_true",
                        help="CurseForge API indirmesi kapali dosyalar icin resmi CDN adresini kullan")
    parser.add_argument("--no-refresh", action="store_true", help="packwiz refresh cagirma")
    parser.add_argument("--all-jars", action="store_true", help="index yerine mods/ icindeki tum jar'lari isle")
    parser.add_argument("--only", default=None, help="Yalnizca verilen alt dizeleri iceren jar'lar (test)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    script_dir = Path(__file__).resolve().parent
    repo = Path(args.repo).resolve() if args.repo else script_dir.parent
    mods_dir = repo / "mods"
    report_path = Path(args.report) if args.report else repo / "resolution-report.json"
    private_path = Path(args.private) if args.private else script_dir / "private-mods.json"
    cache_dir = Path(args.cache) if args.cache else repo / ".packwiz-verify-cache"
    verify_downloads = not args.no_verify_downloads
    api_key = args.cf_key or os.environ.get("CF_API_KEY", "").strip() or None

    def log(message: str) -> None:
        print(message, flush=True)

    if not mods_dir.is_dir():
        raise SystemExit(f"mods klasoru bulunamadi: {mods_dir}")

    wanted = (indexed_mod_names(repo) if not args.all_jars
              else [item.name for item in sorted(mods_dir.glob("*.jar"))])
    if args.only:
        needles = [item.strip().lower() for item in args.only.split(",") if item.strip()]
        wanted = [name for name in wanted if any(needle in name.lower() for needle in needles)]

    jars = [name for name in wanted if (mods_dir / name).is_file()]
    missing = [name for name in wanted if not (mods_dir / name).is_file()]
    log(f"Paket modu: {len(wanted)} | yerel jar: {len(jars)} | eksik yerel jar: {len(missing)}")
    for name in missing:
        log(f"  ! yerelde yok: mods/{name}")

    log("Yerel jar hash'leri hesaplaniyor...")
    digests: dict[str, dict] = {}
    for name in jars:
        digests[name] = hash_path(mods_dir / name)
        digests[name]["size"] = (mods_dir / name).stat().st_size

    entries = resolve_modrinth(jars=jars, digests=digests, log=log)
    unresolved: dict[str, str] = {}

    remaining = [name for name in jars if name not in entries]
    if remaining and api_key:
        cf_entries, cf_unresolved = resolve_curseforge(
            repo=repo, jars=remaining, digests=digests, api_key=api_key,
            verify_downloads=verify_downloads, cache_dir=cache_dir, log=log,
            cdn_fallback=args.cf_cdn_fallback)
        entries.update(cf_entries)
        unresolved.update(cf_unresolved)
    elif remaining:
        log(f"CurseForge anahtari verilmedi; {len(remaining)} jar CurseForge adiminda atlandi")

    leftover = [name for name in jars if name not in entries and name not in unresolved]
    if leftover:
        private_entries, private_unresolved = resolve_private(
            jars=leftover, digests=digests, private_map=load_private_map(private_path),
            verify_downloads=verify_downloads, cache_dir=cache_dir, log=log)
        entries.update(private_entries)
        unresolved.update(private_unresolved)

    for name in jars:
        if name not in entries and name not in unresolved:
            unresolved[name] = "kaynak bulunamadi (Modrinth/CurseForge/ozel esleme)"

    if args.accept_cf_mismatch:
        for record in entries.values():
            record["accepted"] = True

    written: list[dict] = []
    mismatched: list[dict] = []
    if args.report_only:
        log("--report-only: hicbir dosya yazilmadi")
        for name in sorted(entries, key=str.lower):
            record = entries[name]
            written.append({"jar": name, "metaFile": None, "source": record["source"],
                            "name": record["name"], "url": record["url"],
                            "hash-format": record["hashFormat"], "hash": record["hash"],
                            "verified": bool(record.get("verified"))})
    else:
        written, mismatched = write_metafiles(repo=repo, entries=entries, log=log)

    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "packVersion": str(load_pack(repo).get("version") or ""),
        "counts": {
            "index": len(wanted),
            "localJars": len(jars),
            "missingLocal": len(missing),
            "modrinth": len([item for item in written if item["source"] == "modrinth"]),
            "curseforge": len([item for item in written if item["source"] == "curseforge"]),
            "private": len([item for item in written if item["source"] == "private"]),
            "unresolved": len(unresolved),
            "contentMismatch": len(mismatched),
            "unverified": len([item for item in written if not item["verified"]]),
        },
        "mods": written,
        "unresolved": [{"jar": name, "reason": reason} for name, reason in sorted(unresolved.items())],
        "contentMismatch": [{"jar": item["jar"], "url": item["url"], "sha256": item["hash"],
                             "notes": "CurseForge dosyasi yerel jar ile birebir ayni degil"}
                            for item in mismatched],
    }
    if not args.report_only:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")

    counts = report["counts"]
    log("")
    log(f"Kaynak dagilimi: modrinth={counts['modrinth']} curseforge={counts['curseforge']} "
        f"ozel={counts['private']} cozulemeyen={counts['unresolved']} "
        f"icerik-farki={counts['contentMismatch']} dogrulanmamis={counts['unverified']}")
    if unresolved:
        log("Cozulemeyen modlar (elle mudahale gerekli):")
        for name, reason in sorted(unresolved.items()):
            log(f"  - {name}: {reason}")
    if mismatched:
        log("Icerik farki olan CurseForge dosyalari (metafile yazilmadi):")
        for item in mismatched:
            log(f"  - {item['jar']} -> {item['url']}")

    if args.report_only:
        log("--report-only: report dosyasi yazilmadi, dosyalar degistirilmedi")
    elif args.no_refresh:
        log(f"Tamamlandi (refresh atlandi). Rapor: {report_path.name}")
    else:
        run_packwiz_refresh(repo, log)
        log(f"Tamamlandi. Rapor: {report_path.name}")

    return 0 if not unresolved else 2


if __name__ == "__main__":
    sys.exit(main())
