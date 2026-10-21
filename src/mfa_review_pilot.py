"""Small, hand-authored MFA packages for the M3C-1 synthetic review pilot.

These typed interpretations are draft fixture inputs, not automatic extraction,
analyst dispositions or vendor facts. No fixture pre-confirms a fact or signal.
The fixed date makes both freshness behavior and review comparisons reproducible.
"""
from datetime import date

from src.evidence_fact_validation import EvidenceInput, ProposedFact, bind_evidence, segment_id
from src.evidence_intelligence_m3 import Citation, MfaFact, MfaRequirement
from src.mfa_analyst_review import ReviewCase


AS_OF = date(2026, 10, 21)
ACCOUNT_SCOPE = "all human administrators, including emergency accounts"
REQUIREMENT = MfaRequirement(
    "synthetic-customer-privileged-mfa", "2026.1", "Acme Analytics", "production",
    ACCOUNT_SCOPE, ("fido2", "webauthn"), True, True, 90,
)


def _document(document_id, text, *, kind="configuration", observed_on=date(2026, 10, 12),
              service="Acme Analytics", account_scope=ACCOUNT_SCOPE):
    return EvidenceInput(
        document_id, f"{document_id}.txt", text.encode(), "synthetic-v1",
        "Hand-authored synthetic analyst-review pilot; no real vendor evidence",
        date(2026, 10, 15), service, "production", account_scope, observed_on, kind,
    )


def _proposal(document, dimension, line, value=True, *, fact_id=None, uncertainty="", **properties):
    """An explicitly chosen fixture line; no inference or text-pattern extraction."""
    bound = bind_evidence(document)
    part = bound.document.segments[line - 1]
    fact = MfaFact(
        dimension, value, Citation(segment_id(document.document_id, line), part.text),
        document.service, document.environment, document.account_scope,
        document.observed_on, document.evidence_kind, uncertainty, **properties,
    )
    return ProposedFact(fact_id or dimension, fact, bound.fingerprint, part.location)


def _method(document, line, **changes):
    properties = dict(implementation_evidenced=True, origin_bound=True,
                      verifier_bound=True, multifactor=True,
                      authentication_path="primary-admin", active=True)
    properties.update(changes)
    return _proposal(document, "method", line, "fido2", **properties)


def _policy():
    return _document("customer-access-policy", (
        "SYNTHETIC customer policy 2026.1: Acme Analytics production administrative access must use enforced phishing-resistant MFA.\n"
        "Scope includes all human administrators and emergency accounts. Only deployed FIDO2/WebAuthn with origin binding, verifier binding and multiple factors is allowed.\n"
        "Every fallback and recovery route must maintain the same requirement; current complete-population operating tests are required within 90 days."
    ), kind="policy", observed_on=date(2026, 10, 1))


def _strong_documents():
    configuration = _document("complete-idp-export", (
        "SYNTHETIC Acme Analytics production export: MFA is implemented for the complete reconciled inventory of 24 human administrators, including two emergency accounts.\n"
        "Every one of the 24 human administrators is prevented from obtaining an administrative session unless the required MFA challenge succeeds.\n"
        "The active primary-admin path uses deployed FIDO2 security keys plus local PIN; possession and PIN are required, the client checks the origin and the server checks verifier/relying-party binding before issuing a session.\n"
        "The complete authentication-path inventory has every fallback authentication route disabled.\n"
        "Every recovery workflow requires two custodians to register a replacement FIDO2 key plus PIN; the same origin and verifier checks must succeed before any administrative session is issued.\n"
        "The complete account and authentication-path inventories contain no exemptions or exceptions."
    ))
    operating = _document("complete-authentication-test", (
        "SYNTHETIC test executed 2026-10-14: the tester reconciled and exercised all 24 human administrator accounts, including emergency accounts, and every fallback and recovery route. Each session required the deployed FIDO2 key plus PIN and origin/verifier checks; attempts without either factor or with wrong origin/verifier binding failed. No exceptions were found."
    ), kind="test", observed_on=date(2026, 10, 14))
    return (_policy(), configuration, operating)


def _strong_proposals(documents):
    _, configuration, operating = documents
    return (
        _proposal(configuration, "existence", 1), _method(configuration, 3),
        _proposal(configuration, "enforcement", 2), _proposal(operating, "operating", 1),
        _proposal(configuration, "fallback_safe", 4),
        _proposal(configuration, "recovery_safe", 5),
        _proposal(configuration, "exceptions_absent", 6),
    )


def _case(case_id, title, documents, proposals, supporting_ids=()):
    return ReviewCase(case_id, title, REQUIREMENT, tuple(documents), tuple(proposals),
                      AS_OF, tuple(supporting_ids))


def pilot_cases() -> tuple[ReviewCase, ...]:
    """Return fresh, immutable draft packages; no analyst dispositions are seeded."""
    strong_documents = _strong_documents()
    strong_proposals = _strong_proposals(strong_documents)
    strong = _case("strong", "Complete FIDO2 implementation and operating tests",
                   strong_documents, strong_proposals,
                   tuple(item.fact_id for item in strong_proposals))

    primary = _document("routine-admin-export", (
        "SYNTHETIC export for Acme Analytics production: 22 routine human administrators use the central IdP; two emergency human administrators use a separate local management endpoint.\n"
        "The active primary-admin path uses deployed FIDO2 keys plus PIN; the client validates origin and the server validates verifier/relying-party binding, and possession plus PIN verification are both required before issuing sessions.\n"
        "This export contains no configuration or operating assurance for local emergency accounts, fallback routes or recovery workflows."
    ))
    method = _method(primary, 2)
    emergency = _document("emergency-access-configuration", (
        "SYNTHETIC current configuration review: two enabled emergency human administrator accounts bypass MFA and obtain Acme Analytics production administrative sessions using a password-only local login."
    ), observed_on=date(2026, 10, 14))
    bypass = _case("bypass", "Enabled emergency-account MFA bypass",
                   (_policy(), primary, emergency),
                   (method, _proposal(emergency, "enforcement", 1, False,
                                      fact_id="emergency-enforcement-exception")), ("method",))

    admission = _document("vendor-emergency-access-response", (
        "SYNTHETIC vendor response: our two emergency human administrator accounts can bypass MFA and obtain Acme Analytics production administrative sessions with a password only. We have not supplied the local configuration or a test of those accounts."
    ), kind="assertion", observed_on=date(2026, 10, 14))
    reported = _case("reported", "Vendor-reported emergency exception — unverified",
                     (_policy(), primary, admission),
                     (method, _proposal(admission, "enforcement", 1, False,
                                        fact_id="reported-emergency-exception")), ("method",))

    opposing_test = _document("local-account-test", (
        "SYNTHETIC operating test 2026-10-14: two emergency human administrator accounts obtained Acme Analytics production administrative sessions without MFA through the local management endpoint; the complete IdP export says all 24 accounts require MFA."
    ), kind="test", observed_on=date(2026, 10, 14))
    conflict = _case("conflict", "Configuration and operating test disagree",
                     (_policy(), strong_documents[1], opposing_test),
                     (_method(strong_documents[1], 3),
                      _proposal(strong_documents[1], "enforcement", 2,
                                fact_id="configuration-enforcement-claim"),
                      _proposal(opposing_test, "enforcement", 1, False,
                                fact_id="tested-enforcement-exception")), ("method",))

    historical_test = _document("historical-authentication-test", (
        "SYNTHETIC historical test executed 2025-09-15: the tester exercised all 18 human administrator accounts and every fallback and recovery route then recorded. All tested sessions required a deployed FIDO2 key plus PIN and origin/verifier checks. No exceptions were found during that historical period.\n"
        "The test does not cover the current 24-account inventory or any operating period after 2025-09-15."
    ), kind="test", observed_on=date(2025, 9, 15))
    stale_documents = (_policy(), strong_documents[1], historical_test)
    stale_proposals = tuple(item for item in strong_proposals if item.fact.dimension != "operating") + (
        _proposal(historical_test, "operating", 1),)
    stale = _case("stale", "Current configuration with an outdated operating report",
                  stale_documents, stale_proposals,
                  tuple(item.fact_id for item in stale_proposals if item.fact.dimension != "operating"))

    inventory = _document("administrator-inventory", (
        "SYNTHETIC Acme Analytics production inventory lists 24 human administrators, including two emergency accounts.\n"
        "The directory export lists FIDO2 as an available method but provides no per-account enforcement, local endpoint settings or complete fallback and recovery configuration."
    ))
    sampled = _document("sampled-authentication-test", (
        "SYNTHETIC test executed 2026-10-14: three routine human administrator accounts were tested from a 24-account directory; those three used FIDO2 keys plus PIN and passed origin/verifier checks.\n"
        "The tester did not test the remaining 21 administrators, emergency accounts, fallback routes or recovery workflows; no complete-population assurance is offered."
    ), kind="test", observed_on=date(2026, 10, 14))
    coverage_gap = _case("coverage_gap", "Sampled accounts and untested recovery paths",
                         (_policy(), inventory, sampled), (
                             _proposal(sampled, "operating", 1, None,
                                        uncertainty="Only three routine accounts were sampled; complete population was not tested."),
                             _proposal(sampled, "fallback_safe", 2, None,
                                        uncertainty="Fallback workflows were not tested or inventoried."),
                             _proposal(sampled, "recovery_safe", 2, None,
                                        uncertainty="Recovery workflows were not tested or inventoried."),
                         ))

    labs_configuration = _document("analytics-labs-export", (
        "SYNTHETIC configuration covers Acme Analytics Labs, a separate production service with a different identity directory; it does not cover Acme Analytics.\n"
        "Its active primary-admin path requires deployed FIDO2 keys plus PIN, client origin checking and server verifier/relying-party binding; possession and PIN are both required."
    ), service="Acme Analytics Labs")
    labs_test = _document("analytics-labs-test", (
        "SYNTHETIC test 2026-10-14 exercised all six Acme Analytics Labs human administrators and its complete fallback/recovery inventory; the separate Acme Analytics service was excluded. No exceptions were found."
    ), kind="test", service="Acme Analytics Labs", observed_on=date(2026, 10, 14))
    scope_mismatch = _case("scope_mismatch", "Assurance covers a similarly named service",
                           (_policy(), labs_configuration, labs_test),
                           (_method(labs_configuration, 2), _proposal(labs_test, "operating", 1)))

    overview = _document("authentication-service-overview", (
        "SYNTHETIC management response: Acme Analytics supports optional FIDO2 and MFA features for customers. Our internal administrators use the proprietary Secure Challenge method.\n"
        "No deployed factor details, origin/verifier-binding properties, complete administrator coverage, enforcement settings, alternate paths or operating tests were supplied."
    ), kind="assertion")
    unknown = _case("unknown", "Unknown deployed method and optional FIDO2 branding",
                    (_policy(), overview), (
                        _proposal(overview, "method", 1, "secure-challenge",
                                   uncertainty="Method factors and implementation properties are undocumented.",
                                   authentication_path="primary-admin", active=None),
                    ))
    return (strong, bypass, reported, conflict, stale, coverage_gap, scope_mismatch, unknown)
