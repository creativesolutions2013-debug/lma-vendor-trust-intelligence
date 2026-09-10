from src.evidence_state import (
    extraction_matches_file,
    file_changed,
    file_hash,
    form_key,
)


def test_different_reports_generate_different_hashes():
    report_a = b"Synthetic SOC 2 Report A"
    report_b = b"Synthetic SOC 2 Report B"

    hash_a = file_hash(report_a)
    hash_b = file_hash(report_b)

    assert hash_a
    assert hash_b
    assert hash_a != hash_b


def test_same_report_generates_same_hash():
    report = b"Synthetic SOC 2 Report"

    first_hash = file_hash(report)
    second_hash = file_hash(report)

    assert first_hash == second_hash


def test_file_change_is_detected():
    hash_a = file_hash(
        b"Report A"
    )

    hash_b = file_hash(
        b"Report B"
    )

    assert file_changed(
        hash_a,
        hash_b,
    )

    assert not file_changed(
        hash_a,
        hash_a,
    )


def test_extraction_only_matches_original_report():
    report_a_hash = file_hash(
        b"Report A"
    )

    report_b_hash = file_hash(
        b"Report B"
    )

    assert extraction_matches_file(
        report_a_hash,
        report_a_hash,
    )

    assert not extraction_matches_file(
        report_a_hash,
        report_b_hash,
    )


def test_form_keys_are_file_specific():
    hash_a = file_hash(
        b"Report A"
    )

    hash_b = file_hash(
        b"Report B"
    )

    issuer_key_a = form_key(
        "issuer",
        hash_a,
    )

    issuer_key_b = form_key(
        "issuer",
        hash_b,
    )

    notes_key_a = form_key(
        "analyst_notes",
        hash_a,
    )

    assert (
        issuer_key_a
        != issuer_key_b
    )

    assert (
        issuer_key_a
        != notes_key_a
    )


def test_empty_upload_has_safe_defaults():
    assert file_hash(
        b""
    ) is None

    assert not file_changed(
        None,
        None,
    )

    assert not extraction_matches_file(
        None,
        None,
    )

    assert (
        form_key(
            "issuer",
            None,
        )
        == "evidence_form_issuer_manual"
    )