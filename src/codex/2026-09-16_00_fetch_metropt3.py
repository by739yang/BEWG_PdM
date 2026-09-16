#!/usr/bin/env python3
"""Fetch and validate the official UCI MetroPT-3 archive without touching repo data/."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip"
EXPECTED_MEMBERS = {"MetroPT3(AirCompressor).csv", "Data Description_Metro.pdf"}
CACHE_ROOT = Path(os.environ["BEWG_PDM_CACHE_DIR"]).expanduser() if "BEWG_PDM_CACHE_DIR" in os.environ else Path.home() / ".cache" / "BEWG_PdM"
DEFAULT_CACHE = CACHE_ROOT / "metropt3"
LEGACY_CACHE = Path(os.environ.get("TEMP", "")) / "BEWG_PdM_codex" / "metropt3_dataset.zip"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f"not a ZIP archive: {path}")
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        base_names = {Path(n).name for n in names}
        missing = EXPECTED_MEMBERS - base_names
        if missing:
            raise ValueError(f"archive missing expected members: {sorted(missing)}")
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"CRC failure in member: {bad}")
    return names


def atomic_copy(source: Path, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    with source.open("rb") as src, partial.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    os.replace(partial, destination)


def download(destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    req = urllib.request.Request(URL, headers={"User-Agent": "BEWG-PdM-Codex/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out, length=8 * 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        os.replace(partial, destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument(
        "--reuse-legacy-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Atomically adopt the previously downloaded temp cache when valid.",
    )
    args = parser.parse_args()

    cache_dir = args.cache_dir.expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / "metropt3_dataset.zip"
    source = "existing persistent cache"

    if args.force_download or not destination.exists():
        if (
            not args.force_download
            and args.reuse_legacy_cache
            and LEGACY_CACHE.is_file()
        ):
            validate(LEGACY_CACHE)
            atomic_copy(LEGACY_CACHE, destination)
            source = f"validated legacy cache: {LEGACY_CACHE}"
        else:
            download(destination)
            source = URL

    names = validate(destination)
    print(f"archive={destination}")
    print(f"source={source}")
    print(f"bytes={destination.stat().st_size}")
    print(f"sha256={sha256(destination)}")
    print("members=" + " | ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


