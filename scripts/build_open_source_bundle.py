#!/usr/bin/env python3
"""Build a public source archive from OPEN_SOURCE_MANIFEST.txt only."""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "OPEN_SOURCE_MANIFEST.txt"
OUTPUT = ROOT / "release"
VERSION = "0.9.0"
PACKAGE_DIR = f"LatticeScholar-v{VERSION}"


def allowlist() -> list[str]:
    entries: list[str] = []
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "# Explicit exclusions":
            break
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    return (
        any(part in {".git", ".venv", ".data", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build", "release", "promotion-kit"} for part in parts)
        or path.name == ".DS_Store"
        or path.suffix in {".pyc", ".pyo"}
        or path.name.endswith(".egg-info")
    )


def copy_entry(entry: str, destination: Path) -> None:
    source = ROOT / entry.rstrip("/")
    if not source.exists():
        raise FileNotFoundError(f"Manifest entry does not exist: {entry}")
    candidates = [source] if source.is_file() else sorted(source.rglob("*"))
    for item in candidates:
        if item.is_dir() or should_skip(item):
            continue
        if item.is_symlink():
            raise RuntimeError(f"Symlinks are not allowed in the public bundle: {item}")
        relative = item.relative_to(ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    zip_path = OUTPUT / f"{PACKAGE_DIR}-github-source.zip"
    tar_path = OUTPUT / f"{PACKAGE_DIR}-github-source.tar.gz"
    checksums = OUTPUT / "SHA256SUMS.txt"
    for old in (zip_path, tar_path, checksums):
        old.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="latticescholar-public-") as temp:
        staging = Path(temp) / PACKAGE_DIR
        staging.mkdir()
        for entry in allowlist():
            copy_entry(entry, staging)

        file_list = sorted(str(path.relative_to(staging)) for path in staging.rglob("*") if path.is_file())
        (staging / "PUBLIC_FILELIST.txt").write_text("\n".join(file_list) + "\n", encoding="utf-8")

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for item in sorted(staging.rglob("*")):
                if item.is_file():
                    archive.write(item, Path(PACKAGE_DIR) / item.relative_to(staging))
        with tarfile.open(tar_path, "w:gz") as archive:
            archive.add(staging, arcname=PACKAGE_DIR, recursive=True)

    checksums.write_text(
        f"{sha256(zip_path)}  {zip_path.name}\n{sha256(tar_path)}  {tar_path.name}\n",
        encoding="utf-8",
    )
    print(f"Created {zip_path}")
    print(f"Created {tar_path}")
    print(f"Created {checksums}")


if __name__ == "__main__":
    main()
