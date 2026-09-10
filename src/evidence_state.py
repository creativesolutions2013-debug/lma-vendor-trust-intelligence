import hashlib


def file_hash(file_bytes):
    """Return a SHA-256 fingerprint for uploaded evidence bytes."""
    if not file_bytes:
        return None

    return hashlib.sha256(
        file_bytes
    ).hexdigest()


def file_changed(
    previous_hash,
    current_hash,
):
    """
    Return True only when two real uploaded files differ.
    """
    return bool(
        previous_hash
        and current_hash
        and previous_hash != current_hash
    )


def extraction_matches_file(
    extraction_hash,
    current_hash,
):
    """
    Return True only when extraction belongs to the
    currently uploaded document.
    """
    return bool(
        extraction_hash
        and current_hash
        and extraction_hash == current_hash
    )


def form_suffix(file_hash_value):
    """
    Return a short stable value for file-specific
    Streamlit widget keys.
    """
    if not file_hash_value:
        return "manual"

    return file_hash_value[:16]


def form_key(
    field_name,
    file_hash_value,
):
    """
    Build a unique form field key for each evidence file.
    """
    return (
        f"evidence_form_"
        f"{field_name}_"
        f"{form_suffix(file_hash_value)}"
    )