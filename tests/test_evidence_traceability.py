from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import (
    Base,
    Evidence,
    Finding,
    Vendor,
)


def build_test_session():
    engine = create_engine(
        "sqlite:///:memory:"
    )

    Base.metadata.create_all(
        bind=engine
    )

    TestSession = sessionmaker(
        bind=engine
    )

    return TestSession()


def test_finding_persists_evidence_exception_traceability():
    session = build_test_session()

    vendor = Vendor(
        legal_name="Synthetic Vendor LLC",
        display_name="Synthetic Vendor",
    )

    session.add(vendor)
    session.flush()

    evidence = Evidence(
        vendor_id=vendor.id,
        document_type="SOC 2 Type II",
        document_name="Synthetic SOC 2.pdf",
        detected_exceptions=(
            '[{"control_id": "CC7.1", '
            '"description": "Alert review exceeded target.", '
            '"severity": "High"}]'
        ),
    )

    session.add(evidence)
    session.flush()

    finding = Finding(
        vendor_id=vendor.id,
        evidence_id=evidence.id,
        source_exception_index=0,
        source_control_id="CC7.1",
        title="CC7.1 exception",
        description=(
            "Alert review exceeded target."
        ),
        source="Evidence Review",
        severity="High",
        status="Open",
    )

    session.add(finding)
    session.commit()

    persisted = (
        session.query(Finding)
        .filter_by(
            id=finding.id
        )
        .one()
    )

    assert (
        persisted.evidence_id
        == evidence.id
    )

    assert (
        persisted.source_exception_index
        == 0
    )

    assert (
        persisted.source_control_id
        == "CC7.1"
    )

    assert (
        persisted.status
        == "Open"
    )

    session.close()


def test_evidence_exposes_linked_remediation_finding():
    session = build_test_session()

    vendor = Vendor(
        legal_name="Synthetic Vendor LLC",
        display_name="Synthetic Vendor",
    )

    session.add(vendor)
    session.flush()

    evidence = Evidence(
        vendor_id=vendor.id,
        document_type="SOC 2 Type II",
        document_name="Synthetic SOC 2.pdf",
    )

    session.add(evidence)
    session.flush()

    finding = Finding(
        vendor_id=vendor.id,
        evidence_id=evidence.id,
        source_exception_index=1,
        source_control_id="CC6.6",
        title="CC6.6 exception",
        description=(
            "Access review was completed late."
        ),
        source="Evidence Review",
        severity="Moderate",
        status="Open",
        owner="Security Assurance",
        target_date="2026-10-15",
    )

    session.add(finding)
    session.commit()

    persisted_evidence = (
        session.query(Evidence)
        .filter_by(
            id=evidence.id
        )
        .one()
    )

    assert (
        len(persisted_evidence.findings)
        == 1
    )

    linked_finding = (
        persisted_evidence.findings[0]
    )

    assert (
        linked_finding.id
        == finding.id
    )

    assert (
        linked_finding.source_control_id
        == "CC6.6"
    )

    assert (
        linked_finding.source_exception_index
        == 1
    )

    assert (
        linked_finding.owner
        == "Security Assurance"
    )

    assert (
        linked_finding.target_date
        == "2026-10-15"
    )

    session.close()