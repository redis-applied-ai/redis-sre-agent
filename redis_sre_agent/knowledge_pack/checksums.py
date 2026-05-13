"""Checksum helpers for knowledge-pack zip assets."""

from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZipFile


def sha256_bytes(payload: bytes) -> str:
    """Return the sha256 hex digest for one payload."""
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the sha256 hex digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_checksums_for_directory(root: Path, *, exclude: set[str] | None = None) -> dict[str, str]:
    """Build relative-path sha256 digests for files under a directory."""
    excluded = exclude or set()
    checksums: dict[str, str] = {}
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative_path = path.relative_to(root).as_posix()
        if relative_path in excluded:
            continue
        checksums[relative_path] = sha256_file(path)
    return checksums


def write_checksums_file(path: Path, checksums: dict[str, str]) -> None:
    """Write a stable checksums.txt file."""
    lines = [f"{digest}  {relative_path}" for relative_path, digest in sorted(checksums.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_checksums_text(text: str) -> dict[str, str]:
    """Parse checksums.txt contents into a relative-path -> digest mapping."""
    checksums: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        digest, relative_path = line.split("  ", 1)
        checksums[relative_path] = digest
    return checksums


def verify_zip_checksums(zip_path: Path) -> dict[str, str]:
    """Verify a knowledge-pack zip against its embedded checksums file."""
    with ZipFile(zip_path) as archive:
        checksums_text = archive.read("checksums.txt").decode("utf-8")
        checksums = parse_checksums_text(checksums_text)
        for relative_path, expected_digest in checksums.items():
            actual_digest = sha256_bytes(archive.read(relative_path))
            if actual_digest != expected_digest:
                raise ValueError(
                    f"Checksum mismatch for {relative_path}: expected {expected_digest}, got {actual_digest}"
                )
    return checksums
