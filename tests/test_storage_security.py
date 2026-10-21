"""Synthetic path attacks against all local evidence-storage operations."""
import os
from pathlib import Path

import pytest

from src.storage import LocalEvidenceStorage, build_evidence_key, validate_evidence_key


KEY = "vendors/7/evidence/synthetic_report.txt"


def operate(storage, operation, key, **kwargs):
    if operation == "save":
        return storage.save(key, b"SYNTHETIC replacement", **kwargs)
    return getattr(storage, operation)(key, **kwargs)


@pytest.mark.parametrize("operation", ["save", "exists", "delete"])
@pytest.mark.parametrize("key", [
    "", ".", "..", "/tmp/synthetic-report.txt", "../outside.txt",
    "vendors/7/evidence/../outside.txt", "vendors/7/../8/evidence/report.txt",
    "vendors/7/evidence/subdir/report.txt", "vendors//7/evidence/report.txt",
    "vendors/7/evidence//report.txt", "vendors/7/evidence/./report.txt",
    "vendors/7/evidence/..", "vendors/7/evidence/", "vendors/7/evidence/.hidden",
    "vendors/0/evidence/report.txt", "vendors/-7/evidence/report.txt",
    "vendors/07/evidence/report.txt", "vendors/7.0/evidence/report.txt",
    "vendor/7/evidence/report.txt", "vendors/7/other/report.txt",
    r"vendors\7\evidence\report.txt", r"C:\synthetic\report.txt",
    r"\\server\share\report.txt", "file:///tmp/report.txt",
    "vendors/7/evidence/%2e%2e%2foutside.txt", "vendors/7/evidence/report%00.txt",
    "vendors/7/evidence/report.txt:stream", "vendors/7/evidence/report\x00.txt",
    "vendors/7/evidence/report\n.txt", "vendors/7/evidence/report .txt",
    None, Path("vendors/7/evidence/report.txt"),
])
def test_malformed_keys_are_rejected_before_any_storage_creation(tmp_path, operation, key):
    root = tmp_path / "not-created"
    storage = LocalEvidenceStorage(root)
    with pytest.raises(ValueError):
        operate(storage, operation, key)
    assert not root.exists()


@pytest.mark.parametrize("operation", ["save", "exists", "delete"])
@pytest.mark.parametrize("vendor_id", [8, 0, -7, True, "7"])
def test_expected_vendor_must_match_exact_positive_integer(tmp_path, operation, vendor_id):
    root = tmp_path / "not-created"
    storage = LocalEvidenceStorage(root)
    with pytest.raises(ValueError, match="expected vendor"):
        operate(storage, operation, KEY, vendor_id=vendor_id)
    assert not root.exists()


def test_valid_vendor_key_and_legacy_single_leaf_round_trip(tmp_path):
    storage = LocalEvidenceStorage(tmp_path / "private-storage")
    for key in (KEY, "vendors/7/evidence/test.txt", build_evidence_key(7, "SYNTHETIC SOC 2.pdf")):
        assert validate_evidence_key(key, vendor_id=7) == key
        location = storage.save(key, b"SYNTHETIC evidence", vendor_id=7)
        assert Path(location).read_bytes() == b"SYNTHETIC evidence"
        assert storage.exists(key, vendor_id=7)
        storage.save(key, b"SYNTHETIC updated", vendor_id=7)
        assert Path(location).read_bytes() == b"SYNTHETIC updated"
        storage.delete(key, vendor_id=7)
        assert not storage.exists(key, vendor_id=7)
        storage.delete(key, vendor_id=7)  # Already absent is harmless.


@pytest.mark.parametrize("vendor_id", [0, -1, True, "7", None])
def test_builder_rejects_malformed_vendor_ids(vendor_id):
    with pytest.raises(ValueError, match="positive integer"):
        build_evidence_key(vendor_id, "synthetic.txt", unique_id="safe")


@pytest.mark.parametrize("token", ["", "../outside", "/absolute", "a/b", "a\\b", "..", "%2f", True, "x" * 129])
def test_builder_rejects_opaque_id_injection(token):
    with pytest.raises(ValueError, match="opaque evidence ID"):
        build_evidence_key(7, "synthetic.txt", unique_id=token)


@pytest.mark.parametrize("operation", ["save", "exists", "delete"])
@pytest.mark.parametrize("position", ["root", "root-ancestor", "vendors", "vendor", "evidence", "leaf", "dangling-leaf", "in-root-leaf"])
def test_symlink_aliases_are_rejected_without_touching_the_target(tmp_path, operation, position):
    root = tmp_path / "storage"
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "synthetic_report.txt"
    sentinel.write_bytes(b"SYNTHETIC outside sentinel")
    if position == "root":
        root.symlink_to(outside, target_is_directory=True)
    elif position == "root-ancestor":
        alias = tmp_path / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        root = alias / "storage"
    else:
        root.mkdir()
        parts = KEY.split("/")
        depth = {"vendors": 0, "vendor": 1, "evidence": 2}.get(position)
        if depth is not None:
            parent = root.joinpath(*parts[:depth])
            parent.mkdir(parents=True, exist_ok=True)
            (parent / parts[depth]).symlink_to(outside, target_is_directory=True)
        else:
            parent = root.joinpath(*parts[:-1])
            parent.mkdir(parents=True)
            target = sentinel
            if position == "dangling-leaf":
                target = outside / "not-created.txt"
            elif position == "in-root-leaf":
                target = root / "other-synthetic.txt"
                target.write_bytes(b"SYNTHETIC in-root target")
            (parent / parts[-1]).symlink_to(target)
    before = sentinel.read_bytes()
    storage = LocalEvidenceStorage(root)
    with pytest.raises(ValueError):
        operate(storage, operation, KEY)
    assert sentinel.read_bytes() == before
    assert not (outside / "not-created.txt").exists()
    assert not (outside / "storage").exists()


@pytest.mark.parametrize("operation", ["save", "exists", "delete"])
def test_hardlinked_leaf_cannot_modify_or_delete_outside_object(tmp_path, operation):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"SYNTHETIC outside sentinel")
    root = tmp_path / "storage"
    leaf = root / KEY
    leaf.parent.mkdir(parents=True)
    os.link(outside, leaf)
    with pytest.raises(ValueError, match="without links"):
        operate(LocalEvidenceStorage(root), operation, KEY)
    assert outside.read_bytes() == b"SYNTHETIC outside sentinel"
    assert leaf.exists()


@pytest.mark.parametrize("operation", ["save", "exists", "delete"])
def test_directory_leaf_is_never_treated_as_an_evidence_file(tmp_path, operation):
    root = tmp_path / "storage"
    (root / KEY).mkdir(parents=True)
    with pytest.raises(ValueError, match="regular file"):
        operate(LocalEvidenceStorage(root), operation, KEY)
    assert (root / KEY).is_dir()


@pytest.mark.parametrize("operation", ["save", "exists", "delete"])
def test_open_parent_stays_anchored_during_symlink_substitution(tmp_path, monkeypatch, operation):
    root = tmp_path / "storage"
    storage = LocalEvidenceStorage(root)
    storage.save(KEY, b"SYNTHETIC original")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / Path(KEY).name
    sentinel.write_bytes(b"SYNTHETIC outside sentinel")
    actual = root / "vendors/7/evidence"
    moved = actual.with_name("retained-evidence")
    original_leaf = storage._leaf

    def substitute(parent, leaf):
        actual.rename(moved)
        actual.symlink_to(outside, target_is_directory=True)
        return original_leaf(parent, leaf)

    monkeypatch.setattr(storage, "_leaf", substitute)
    operate(storage, operation, KEY)
    assert sentinel.read_bytes() == b"SYNTHETIC outside sentinel"
    if operation == "save":
        assert (moved / Path(KEY).name).read_bytes() == b"SYNTHETIC replacement"
    elif operation == "delete":
        assert not (moved / Path(KEY).name).exists()


def test_leaf_symlink_swapped_after_stat_cannot_be_followed_by_save(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    storage = LocalEvidenceStorage(root)
    storage.save(KEY, b"SYNTHETIC original")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"SYNTHETIC outside sentinel")
    original_leaf = storage._leaf

    def substitute(parent, leaf):
        result = original_leaf(parent, leaf)
        (root / KEY).unlink()
        (root / KEY).symlink_to(outside)
        return result

    monkeypatch.setattr(storage, "_leaf", substitute)
    with pytest.raises(ValueError, match="Unsafe"):
        storage.save(KEY, b"SYNTHETIC must not overwrite outside")
    assert outside.read_bytes() == b"SYNTHETIC outside sentinel"


def test_leaf_hardlink_swapped_after_stat_is_rejected_before_truncation(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    storage = LocalEvidenceStorage(root)
    storage.save(KEY, b"SYNTHETIC original")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"SYNTHETIC outside sentinel")
    original_leaf = storage._leaf

    def substitute(parent, leaf):
        result = original_leaf(parent, leaf)
        (root / KEY).unlink()
        os.link(outside, root / KEY)
        return result

    monkeypatch.setattr(storage, "_leaf", substitute)
    with pytest.raises(ValueError, match="without links"):
        storage.save(KEY, b"SYNTHETIC must not overwrite outside")
    assert outside.read_bytes() == b"SYNTHETIC outside sentinel"


def test_absent_read_side_does_not_create_storage(tmp_path):
    root = tmp_path / "not-created"
    storage = LocalEvidenceStorage(root)
    assert storage.exists(KEY) is False
    storage.delete(KEY)
    assert not root.exists()


def test_storage_requires_private_directory_and_secure_platform_features(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="dedicated"):
        LocalEvidenceStorage(Path(tmp_path).anchor)
    monkeypatch.delattr(os, "O_NOFOLLOW")
    storage = LocalEvidenceStorage(tmp_path / "not-created")
    with pytest.raises(RuntimeError, match="no-follow"):
        storage.save(KEY, b"SYNTHETIC content")
    assert not storage.base_dir.exists()
