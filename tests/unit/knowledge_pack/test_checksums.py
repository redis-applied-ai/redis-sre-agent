from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from redis_sre_agent.knowledge_pack.checksums import (
    build_checksums_for_directory,
    parse_checksums_text,
    verify_zip_checksums,
    write_checksums_file,
)


def test_parse_checksums_text_round_trips():
    checksums = {"manifest.json": "abc123", "restore/data.ndjson": "def456"}
    lines = "abc123  manifest.json\ndef456  restore/data.ndjson\n"

    assert parse_checksums_text(lines) == checksums


def test_verify_zip_checksums_accepts_matching_archive(tmp_path: Path):
    root = tmp_path / "pack"
    root.mkdir()
    (root / "manifest.json").write_text('{"pack_id":"abc"}\n', encoding="utf-8")
    restore_dir = root / "restore"
    restore_dir.mkdir()
    (restore_dir / "knowledge_chunks.ndjson").write_text("{}\n", encoding="utf-8")

    checksums = build_checksums_for_directory(root, exclude={"checksums.txt"})
    write_checksums_file(root / "checksums.txt", checksums)

    zip_path = tmp_path / "pack.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            archive.write(path, path.relative_to(root).as_posix())

    assert verify_zip_checksums(zip_path) == checksums


def test_verify_zip_checksums_rejects_modified_archive(tmp_path: Path):
    zip_path = tmp_path / "pack.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", '{"pack_id":"abc"}\n')
        archive.writestr("checksums.txt", "badcafe  manifest.json\n")

    with pytest.raises(ValueError, match="Checksum mismatch for manifest.json"):
        verify_zip_checksums(zip_path)
