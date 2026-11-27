"""Immutable synthetic vendor delivery metadata, separate from analyst capture.

The in-transaction helpers are private server composition. They require the
caller's existing authorized SQL transaction and session lease, never a browser
DTO or a standalone authorization result. Custody retains the original parents.
"""
from datetime import date, datetime
from hashlib import sha256
from hmac import compare_digest
import json
import re

from sqlalchemy import func, insert, select, text

from src.synthetic_custody_guards import _schema


MAX_HANDOFF_METADATA_BYTES = 4096
TABLE_NAME = "synthetic_vendor_handoffs"
_FIELDS = frozenset(("schema_version", "invitation_id", "vendor_issuer", "vendor_subject",
    "vendor_session_id", "vendor_role", "submitted_at", "kind",
    "observed_on", "requirement_id", "inviter_issuer", "inviter_subject", "inviter_session_id"))


def _text(value, limit):
    if (type(value) is not str or not 1 <= len(value) <= limit or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("Invalid synthetic handoff metadata.")


def encode_handoff_metadata(metadata):
    """Validate and encode exactly the versioned, bounded server-owned contract."""
    if type(metadata) is not dict or set(metadata) != _FIELDS or type(metadata["schema_version"]) is not int or metadata["schema_version"] != 1:
        raise ValueError("Unsupported synthetic handoff metadata.")
    for key, limit in (("invitation_id", 32), ("vendor_issuer", 500), ("vendor_subject", 255),
                       ("vendor_session_id", 80), ("vendor_role", 80), ("submitted_at", 64),
                       ("requirement_id", 80), ("inviter_issuer", 500), ("inviter_subject", 255),
                       ("inviter_session_id", 80)):
        _text(metadata[key], limit)
    if (re.fullmatch(r"[0-9a-f]{32}", metadata["invitation_id"]) is None
            or metadata["vendor_subject"] != "synthetic-vendor" or metadata["vendor_role"] != "Authenticated synthetic invitee"
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", metadata["requirement_id"]) is None
            or metadata["kind"] not in ("policy", "assertion", "configuration", "test")
            or any(re.fullmatch(r"sid_[A-Za-z0-9_-]{43}", metadata[key]) is None
                   for key in ("vendor_session_id", "inviter_session_id"))):
        raise ValueError("Invalid synthetic handoff provenance.")
    stamp = datetime.fromisoformat(metadata["submitted_at"])
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Synthetic delivery time requires a timezone.")
    observed = metadata["observed_on"]
    if observed is not None and (type(observed) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", observed) is None
                                 or date.fromisoformat(observed).isoformat() != observed or date.fromisoformat(observed) > stamp.date()):
        raise ValueError("Invalid synthetic observation date.")
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    if not 1 <= len(encoded) <= MAX_HANDOFF_METADATA_BYTES:
        raise ValueError("Synthetic handoff metadata exceeds its bound.")
    return encoded


def _decode_metadata(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate synthetic metadata field.")
            result[key] = value
        return result
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_HANDOFF_METADATA_BYTES:
        raise ValueError("Invalid bounded synthetic handoff.")
    metadata = json.loads(payload.decode("ascii"), object_pairs_hook=unique)
    if encode_handoff_metadata(metadata) != payload:
        raise ValueError("Synthetic handoff metadata is noncanonical.")
    return metadata


def synthetic_handoff_guard_statements(dialect, schema=None):
    quote = dialect.identifier_preparer.quote
    prefix = quote(schema) + "." if schema else ""
    relation = lambda name: prefix + quote(name)
    handoffs = relation(TABLE_NAME)
    anchor = (f"SELECT 1 FROM {relation('synthetic_evidence_objects')} c WHERE c.evidence_id=NEW.evidence_id "
              "AND c.organization_id=NEW.organization_id AND c.vendor_id=NEW.vendor_id "
              "AND c.engagement_id=NEW.engagement_id AND c.assessment_id=NEW.assessment_id "
              "AND c.generation=NEW.generation AND c.sha256=NEW.sha256")
    if dialect.name == "sqlite":
        statements = [f"CREATE TRIGGER {relation('m7_handoff_no_' + action)} BEFORE {action.upper()} ON {handoffs} "
                      "BEGIN SELECT RAISE(ABORT, 'Synthetic handoff provenance is immutable'); END"
                      for action in ("update", "delete")]
        statements.append(f"CREATE TRIGGER {relation('m7_handoff_insert')} BEFORE INSERT ON {handoffs} BEGIN "
            f"SELECT CASE WHEN EXISTS (SELECT 1 FROM {handoffs} WHERE evidence_id=NEW.evidence_id) "
            "THEN RAISE(ABORT, 'Synthetic handoff cannot be replaced') END; "
            "SELECT CASE WHEN typeof(NEW.metadata_payload)<>'blob' OR length(NEW.metadata_sha256)<>64 "
            "OR NEW.metadata_sha256 GLOB '*[^0-9a-f]*' OR length(NEW.generation)<>32 OR NEW.generation GLOB '*[^0-9a-f]*' "
            "OR length(NEW.sha256)<>64 OR NEW.sha256 GLOB '*[^0-9a-f]*' "
            f"OR NOT EXISTS ({anchor}) THEN RAISE(ABORT, 'Invalid synthetic handoff linkage') END; END")
        return tuple(statements)
    if dialect.name != "postgresql":
        raise RuntimeError("Synthetic handoff provenance requires SQLite or PostgreSQL.")
    immutable = relation("m7_handoff_reject_mutation")
    validate = relation("m7_handoff_validate_insert")
    statements = [
        f"CREATE OR REPLACE FUNCTION {immutable}() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog "
        "AS $$ BEGIN RAISE EXCEPTION 'Synthetic handoff provenance is immutable'; END; $$",
        f"CREATE OR REPLACE FUNCTION {validate}() RETURNS trigger LANGUAGE plpgsql VOLATILE SET search_path=pg_catalog AS $$ BEGIN "
        f"PERFORM evidence_id FROM {relation('synthetic_evidence_objects')} WHERE evidence_id=NEW.evidence_id FOR SHARE; "
        "IF NEW.metadata_sha256 !~ '^[0-9a-f]{64}$' OR NEW.generation !~ '^[0-9a-f]{32}$' OR NEW.sha256 !~ '^[0-9a-f]{64}$' "
        f"OR NOT EXISTS ({anchor}) THEN RAISE EXCEPTION 'Invalid synthetic handoff linkage'; END IF; RETURN NEW; END; $$",
    ]
    for name, operation, function in (("m7_handoff_insert", "INSERT", validate),
                                     ("m7_handoff_no_mutation", "UPDATE OR DELETE", immutable),
                                     ("m7_handoff_no_truncate", "TRUNCATE", immutable)):
        statements.extend((f"CREATE TRIGGER {quote(name)} BEFORE {operation} ON {handoffs} "
            f"FOR EACH {'STATEMENT' if operation == 'TRUNCATE' else 'ROW'} EXECUTE FUNCTION {function}()",
            f"ALTER TABLE {handoffs} ENABLE ALWAYS TRIGGER {quote(name)}"))
    return tuple(statements)


def install_synthetic_handoff_guards(table, connection, **_):
    for statement in synthetic_handoff_guard_statements(connection.dialect, _schema(table, connection)):
        connection.exec_driver_sql(statement)


def require_synthetic_handoff_guards(connection, table):
    dialect, schema = connection.dialect.name, _schema(table, connection)
    if dialect == "sqlite":
        quote = connection.dialect.identifier_preparer.quote
        prefix = quote(schema) + "." if schema else ""
        tables = connection.exec_driver_sql(f"PRAGMA {quote(schema or 'main')}.table_list").all()
        if len([row for row in tables if len(row) >= 5 and row[0] == (schema or "main")
                and row[1] == TABLE_NAME and row[2] == "table" and row[4] == 1]) != 1:
            raise PermissionError("Synthetic handoff guards are unavailable.")
        names = connection.exec_driver_sql(f"SELECT name FROM {prefix}sqlite_master WHERE type='trigger' AND tbl_name='{TABLE_NAME}'").scalars().all()
        if not {"m7_handoff_insert", "m7_handoff_no_update", "m7_handoff_no_delete"} <= set(names):
            raise PermissionError("Synthetic handoff guards are unavailable.")
        return
    if dialect != "postgresql":
        raise PermissionError("Synthetic handoff guards are unavailable.")
    rows = connection.execute(text("""SELECT t.tgname,t.tgtype FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
        WHERE n.nspname=:schema AND pn.nspname=:schema AND c.relname='synthetic_vendor_handoffs'
          AND t.tgenabled='A' AND NOT t.tgisinternal AND t.tgqual IS NULL"""), {"schema": schema}).all()
    if not {("m7_handoff_insert", 7), ("m7_handoff_no_mutation", 27), ("m7_handoff_no_truncate", 34)} <= {tuple(row) for row in rows}:
        raise PermissionError("Synthetic handoff guards are unavailable.")


def _verified_receipt(session, scope, receipt):
    from src.assessment_evidence_access import EvidenceReadRequest
    from src.synthetic_evidence_custody import SyntheticEvidenceReceipt, _retrieve_in_authorized_transaction
    if type(receipt) is not SyntheticEvidenceReceipt or receipt.organization_id != scope.identity.organization_id or receipt.engagement_id not in scope.engagement_ids:
        raise PermissionError("Synthetic handoff is unavailable.")
    request = EvidenceReadRequest(receipt.organization_id, receipt.engagement_id, receipt.vendor_id,
                                  receipt.assessment_id, receipt.evidence_id)
    verified = _retrieve_in_authorized_transaction(session, scope, request, receipt.generation)
    if verified.receipt != receipt:
        raise PermissionError("Synthetic handoff is unavailable.")


def record_handoff_in_transaction(session, scope, receipt, metadata):
    """Append server-validated delivery provenance in the held analyst transaction."""
    from src.db import SyntheticVendorHandoff
    require_synthetic_handoff_guards(session.connection(), SyntheticVendorHandoff.__table__)
    _verified_receipt(session, scope, receipt)
    payload = encode_handoff_metadata(metadata)
    values = {name: getattr(receipt, name) for name in ("evidence_id", "organization_id", "vendor_id", "engagement_id", "assessment_id", "generation", "sha256")}
    session.execute(insert(SyntheticVendorHandoff).values(**values, metadata_payload=payload, metadata_sha256=sha256(payload).hexdigest()))
    if handoff_in_transaction(session, scope, receipt) != metadata:
        raise PermissionError("Synthetic handoff verification failed.")


def handoff_in_transaction(session, scope, receipt):
    """Read only exact current custody-linked provenance within the held scope."""
    from src.db import SyntheticVendorHandoff
    require_synthetic_handoff_guards(session.connection(), SyntheticVendorHandoff.__table__)
    _verified_receipt(session, scope, receipt)
    table = SyntheticVendorHandoff
    row = session.execute(select(table.organization_id, table.vendor_id, table.engagement_id,
        table.assessment_id, table.generation, table.sha256, func.substr(table.metadata_payload, 1, MAX_HANDOFF_METADATA_BYTES + 1),
        func.substr(table.metadata_sha256, 1, 65)).where(table.evidence_id == receipt.evidence_id)).one_or_none()
    if row is None:
        return None
    if tuple(row[:6]) != tuple(getattr(receipt, name) for name in ("organization_id", "vendor_id", "engagement_id", "assessment_id", "generation", "sha256")):
        raise PermissionError("Synthetic handoff linkage differs.")
    payload, digest = row[6:]
    if type(payload) is not bytes or type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None or not compare_digest(sha256(payload).hexdigest(), digest):
        raise PermissionError("Synthetic handoff metadata differs.")
    return _decode_metadata(payload)
