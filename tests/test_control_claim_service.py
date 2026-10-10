import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.authz import (
    Principal,
    ROLE_ANALYST,
    ROLE_VIEWER,
)
from src.control_claim_review import (
    AnalystClaimConfirmation,
    review_control_claim_candidate,
)
from src.control_claim_service import (
    load_accepted_control_claims,
    load_control_claim_history,
    save_control_claim,
)
from src.control_claims import (
    ControlClaimCandidate,
)
from src.db import (
    Assessment,
    AuditLog,
    Base,
    ControlClaimRecord,
    Evidence,
    Vendor,
)


def make_session():
    engine = create_engine(
        "sqlite:///:memory:"
    )

    Base.metadata.create_all(
        engine
    )

    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )()


def make_principal():
    return Principal(
        subject="analyst-123",
        display_name="Test Analyst",
        email="analyst@example.com",
        role=ROLE_ANALYST,
    )


def seed_context(
    session,
):
    vendor = Vendor(
        legal_name="Example Vendor LLC",
        display_name="Example Vendor",
    )

    session.add(
        vendor
    )

    session.flush()

    assessment = Assessment(
        vendor_id=vendor.id,
        assessment_type=(
            "Security Assessment"
        ),
    )

    session.add(
        assessment
    )

    session.flush()

    evidence = Evidence(
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        document_type="SOC 2 Type II",
        document_name="Example SOC 2",
        extraction_confidence=0.92,
    )

    session.add(
        evidence
    )

    session.flush()

    return (
        vendor,
        assessment,
        evidence,
    )


def make_candidate(
    *,
    control_id="IAM-01",
    confidence=0.92,
):
    return ControlClaimCandidate(
        control_id=control_id,
        statement=(
            "Logical access is approved, "
            "provisioned, reviewed, and revoked."
        ),
        source_reference=(
            "SOC2 p.42 CC6.1"
        ),
        confidence=confidence,
    )


def make_review(
    *,
    evidence_id: int,
    principal: Principal,
    control_id="IAM-01",
    confidence=0.92,
    exception_present=False,
):
    return review_control_claim_candidate(
        evidence_id,
        make_candidate(
            control_id=control_id,
            confidence=confidence,
        ),
        AnalystClaimConfirmation(
            covered=True,
            tested=True,
            scope_matches=True,
            service_matches=True,
            exception_present=(
                exception_present
            ),
            confirmed_by=(
                principal.subject
            ),
            analyst_rationale=(
                "Reviewed source evidence and "
                "confirmed control coverage, "
                "testing, scope, and service "
                "alignment."
            ),
        ),
        allowed_control_ids=(
            "IAM-01",
            "PAM-01",
            "VM-01",
        ),
    )


def test_save_control_claim_persists_record():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    review = make_review(
        evidence_id=evidence.id,
        principal=principal,
    )

    saved = save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=review,
        principal=principal,
    )

    session.commit()

    record = (
        session.query(
            ControlClaimRecord
        )
        .filter_by(
            id=saved.id
        )
        .one()
    )

    assert (
        record.vendor_id
        == vendor.id
    )

    assert (
        record.assessment_id
        == assessment.id
    )

    assert (
        record.evidence_id
        == evidence.id
    )

    assert (
        record.control_id
        == "IAM-01"
    )

    assert record.covered is True
    assert record.tested is True
    assert record.scope_matches is True
    assert record.service_matches is True
    assert record.exception_present is False

    assert (
        record.generation_status
        == "ACCEPTED"
    )

    assert (
        record.human_confirmed
        is True
    )

    assert (
        record.confirmed_by
        == "analyst-123"
    )

    assert (
        record.claim_policy_version
        == "CG-1.1"
    )

    assert (
        record.review_policy_version
        == "CCR-1.0"
    )

    session.close()


def test_save_control_claim_creates_audit_event():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    saved = save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=make_review(
            evidence_id=evidence.id,
            principal=principal,
        ),
        principal=principal,
    )

    session.commit()

    event = (
        session.query(
            AuditLog
        )
        .filter_by(
            action="control_claim.record"
        )
        .one()
    )

    assert (
        event.object_type
        == "control_claim"
    )

    assert (
        event.object_id
        == str(saved.id)
    )

    assert (
        event.vendor_id
        == vendor.id
    )

    session.close()


def test_loader_reconstructs_evidence_control_claim():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=make_review(
            evidence_id=evidence.id,
            principal=principal,
        ),
        principal=principal,
    )

    session.commit()

    claims = load_accepted_control_claims(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
    )

    assert len(
        claims
    ) == 1

    claim = claims[0]

    assert (
        claim.evidence_id
        == evidence.id
    )

    assert (
        claim.control_id
        == "IAM-01"
    )

    assert claim.covered is True
    assert claim.tested is True
    assert claim.scope_matches is True
    assert claim.service_matches is True
    assert claim.exception_present is False

    assert (
        claim.extraction_confidence
        == 0.92
    )

    session.close()


def test_loader_preserves_confirmed_exception():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=make_review(
            evidence_id=evidence.id,
            principal=principal,
            exception_present=True,
        ),
        principal=principal,
    )

    session.commit()

    claims = load_accepted_control_claims(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
    )

    assert len(
        claims
    ) == 1

    assert (
        claims[0].exception_present
        is True
    )

    session.close()


def test_loader_uses_latest_claim_for_same_evidence_control_pair():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    first = make_review(
        evidence_id=evidence.id,
        principal=principal,
        exception_present=True,
    )

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=first,
        principal=principal,
    )

    second = make_review(
        evidence_id=evidence.id,
        principal=principal,
        exception_present=False,
    )

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=second,
        principal=principal,
    )

    session.commit()

    claims = load_accepted_control_claims(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
    )

    assert len(
        claims
    ) == 1

    assert (
        claims[0].exception_present
        is False
    )

    session.close()


def test_unaccepted_review_cannot_be_persisted():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    incomplete_review = (
        review_control_claim_candidate(
            evidence.id,
            make_candidate(),
            AnalystClaimConfirmation(
                covered=True,
                tested=None,
                scope_matches=True,
                service_matches=True,
                exception_present=False,
                confirmed_by=(
                    principal.subject
                ),
                analyst_rationale=(
                    "Testing status could not "
                    "be confirmed."
                ),
            ),
            allowed_control_ids=(
                "IAM-01",
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="accepted control claim",
    ):
        save_control_claim(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            review=incomplete_review,
            principal=principal,
        )

    session.close()


def test_viewer_cannot_persist_control_claim():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    analyst = make_principal()

    review = make_review(
        evidence_id=evidence.id,
        principal=analyst,
    )

    viewer = Principal(
        subject="viewer-1",
        display_name="Viewer",
        email="viewer@example.com",
        role=ROLE_VIEWER,
    )

    with pytest.raises(
        PermissionError
    ):
        save_control_claim(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            review=review,
            principal=viewer,
        )

    session.close()


def test_confirming_identity_must_match_authenticated_principal():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    mismatched_review = (
        review_control_claim_candidate(
            evidence.id,
            make_candidate(),
            AnalystClaimConfirmation(
                covered=True,
                tested=True,
                scope_matches=True,
                service_matches=True,
                exception_present=False,
                confirmed_by=(
                    "different-user"
                ),
                analyst_rationale=(
                    "Evidence reviewed."
                ),
            ),
            allowed_control_ids=(
                "IAM-01",
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="authenticated principal",
    ):
        save_control_claim(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            review=mismatched_review,
            principal=principal,
        )

    session.close()


def test_history_includes_evidence_and_provenance():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=make_review(
            evidence_id=evidence.id,
            principal=principal,
        ),
        principal=principal,
    )

    session.commit()

    history = load_control_claim_history(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
    )

    assert len(history) == 1

    item = history[0]

    assert item.control_id == "IAM-01"
    assert item.evidence_id == evidence.id
    assert item.evidence_name == "Example SOC 2"
    assert item.evidence_type == "SOC 2 Type II"

    assert item.confirmed_by == "analyst-123"
    assert item.confidence == 0.92

    assert item.claim_policy_version == "CG-1.1"
    assert item.review_policy_version == "CCR-1.0"

    assert item.is_current is True

    session.close()


def test_history_marks_latest_record_current():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=make_review(
            evidence_id=evidence.id,
            principal=principal,
            exception_present=True,
        ),
        principal=principal,
    )

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=make_review(
            evidence_id=evidence.id,
            principal=principal,
            exception_present=False,
        ),
        principal=principal,
    )

    session.commit()

    history = load_control_claim_history(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        control_id="IAM-01",
    )

    assert len(history) == 2

    assert history[0].is_current is True
    assert history[0].exception_present is False

    assert history[1].is_current is False
    assert history[1].exception_present is True

    session.close()


def test_history_can_filter_by_control():
    session = make_session()

    vendor, assessment, evidence = (
        seed_context(
            session
        )
    )

    principal = make_principal()

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=make_review(
            evidence_id=evidence.id,
            principal=principal,
            control_id="IAM-01",
        ),
        principal=principal,
    )

    save_control_claim(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        review=make_review(
            evidence_id=evidence.id,
            principal=principal,
            control_id="VM-01",
        ),
        principal=principal,
    )

    session.commit()

    history = load_control_claim_history(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        control_id="IAM-01",
    )

    assert len(history) == 1
    assert history[0].control_id == "IAM-01"

    session.close()

