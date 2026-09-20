from pathlib import Path

import pytest

from src.storage import (
    LocalEvidenceStorage,
    _safe_filename,
    build_evidence_key,
    get_evidence_storage,
)


def test_safe_filename_removes_path_and_unsafe_characters():
    assert _safe_filename("../../SOC 2 Report (Final).pdf") == (
        "SOC_2_Report_Final_.pdf"
    )


def test_build_evidence_key_is_vendor_scoped_and_deterministic_with_id():
    key = build_evidence_key(
        42,
        "SOC 2.pdf",
        unique_id="abc123",
    )

    assert key == "vendors/42/evidence/abc123_SOC_2.pdf"


def test_local_storage_round_trip(tmp_path):
    storage = LocalEvidenceStorage(str(tmp_path))
    key = "vendors/1/evidence/test.txt"
    content = b"synthetic evidence"

    location = storage.save(key, content)

    assert Path(location).read_bytes() == content
    assert storage.exists(key) is True

    storage.delete(key)

    assert storage.exists(key) is False


def test_get_storage_defaults_to_local(monkeypatch, tmp_path):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("EVIDENCE_LOCAL_DIR", str(tmp_path))

    storage = get_evidence_storage()

    assert isinstance(storage, LocalEvidenceStorage)


def test_get_storage_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "unknown")

    with pytest.raises(ValueError, match="Unsupported STORAGE_BACKEND"):
        get_evidence_storage()
