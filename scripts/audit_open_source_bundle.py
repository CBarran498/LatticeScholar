#!/usr/bin/env python3
"""Fail closed when a public source ZIP contains private or unsafe material."""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path, PurePosixPath


FORBIDDEN_PARTS = {
    ".git",
    ".venv",
    ".data",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "release",
    "promotion-kit",
    "htmlcov",
}
FORBIDDEN_NAMES = {".env", ".DS_Store", ".coverage", "coverage.xml"}
SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{70,})"),
    "AWS access key": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "OpenAI-style live key": re.compile(rb"sk-(?!your-key|test|example)[A-Za-z0-9_-]{32,}"),
    "Stripe live secret": re.compile(rb"sk_live_[A-Za-z0-9]{20,}"),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "Slack token": re.compile(rb"xox[baprs]-[0-9A-Za-z-]{24,}"),
}
REQUIRED_SUFFIXES = {
    "LICENSE",
    "NOTICE",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "OPEN_SOURCE_MANIFEST.txt",
    "PUBLIC_FILELIST.txt",
    "pyproject.toml",
}


def main() -> None:
    archive_path = Path(sys.argv[1] if len(sys.argv) > 1 else "release/LatticeScholar-v0.9.0-github-source.zip")
    errors: list[str] = []
    file_names: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        roots = {PurePosixPath(info.filename).parts[0] for info in entries if info.filename}
        if len(roots) != 1:
            errors.append(f"expected one archive root, found {sorted(roots)}")
        for info in entries:
            path = PurePosixPath(info.filename)
            parts = path.parts
            if path.is_absolute() or ".." in parts:
                errors.append(f"unsafe path: {info.filename}")
                continue
            relative_parts = parts[1:]
            if any(part in FORBIDDEN_PARTS for part in relative_parts):
                errors.append(f"forbidden directory: {info.filename}")
            if path.name in FORBIDDEN_NAMES or path.suffix in {".pyc", ".pyo"}:
                errors.append(f"forbidden file: {info.filename}")
            if info.is_dir():
                continue
            file_names.append(info.filename)
            data = archive.read(info)
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(data):
                    errors.append(f"possible {label}: {info.filename}")

        present = {PurePosixPath(name).name for name in file_names}
        for required in REQUIRED_SUFFIXES:
            if required not in present:
                errors.append(f"missing required file: {required}")

    if errors:
        print("Public bundle audit failed:")
        for error in errors:
            print("-", error)
        raise SystemExit(1)
    print(f"Public bundle audit passed: {len(file_names)} files, no forbidden paths or secret patterns")


if __name__ == "__main__":
    main()
