from src.db import EvidenceRequestPackage


def test_evidence_request_model_table():
    assert (
        EvidenceRequestPackage.__tablename__
        == "evidence_request_packages"
    )


def test_evidence_request_model_fields():
    columns = {
        column.name
        for column
        in EvidenceRequestPackage.__table__.columns
    }

    expected = {
        "id",
        "vendor_id",
        "assessment_id",
        "status",
        "requested_items_json",
        "validation_items_json",
        "avoided_requests_json",
        "analyst_notes",
        "created_by",
        "created_at",
        "sent_by",
        "sent_at",
        "received_at",
        "closed_at",
    }

    assert expected <= columns
