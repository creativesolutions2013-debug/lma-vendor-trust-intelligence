import json
from dataclasses import dataclass
from typing import Iterable, Tuple

from src.control_claims import (
    ControlClaimCandidate,
)


ADAPTER_POLICY_VERSION = "ECA-1.0"


@dataclass(frozen=True)
class EvidenceClaimCandidateResult:
    evidence_id: int

    candidates: Tuple[
        ControlClaimCandidate,
        ...,
    ]

    policy_version: str = (
        ADAPTER_POLICY_VERSION
    )


def _safe_json_list(
    value,
) -> list:
    if not value:
        return []

    if isinstance(
        value,
        list,
    ):
        return value

    if not isinstance(
        value,
        str,
    ):
        return []

    try:
        parsed = json.loads(
            value
        )

    except (
        TypeError,
        json.JSONDecodeError,
    ):
        return []

    return (
        parsed
        if isinstance(
            parsed,
            list,
        )
        else []
    )


def _normalized_confidence(
    evidence,
) -> float:
    value = getattr(
        evidence,
        "extraction_confidence",
        None,
    )

    try:
        value = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return 0.0

    return max(
        0.0,
        min(
            value,
            1.0,
        ),
    )


def _source_reference(
    evidence,
    *,
    control_id: str,
) -> str:
    document_name = (
        getattr(
            evidence,
            "document_name",
            "",
        )
        or "Evidence"
    )

    return (
        f"{document_name} "
        f"[Evidence ID {evidence.id}] "
        f"[Control {control_id}]"
    )


def _exception_candidates(
    evidence,
    allowed_control_ids: set[str],
) -> list[
    ControlClaimCandidate
]:
    """
    Create conservative candidates from explicitly detected
    control exceptions.

    An exception tells us that the document references a control,
    but it does not prove:
    - complete control coverage,
    - successful operating-effectiveness testing,
    - service alignment,
    - scope alignment.

    Those facts therefore remain None.
    """

    exception_rows = (
        _safe_json_list(
            getattr(
                evidence,
                "detected_exceptions",
                None,
            )
        )
    )

    candidates = []

    for row in exception_rows:

        if not isinstance(
            row,
            dict,
        ):
            continue

        control_id = (
            row.get(
                "control_id",
                ""
            )
            or ""
        ).strip().upper()

        if (
            not control_id
            or control_id
            not in allowed_control_ids
        ):
            continue

        description = (
            row.get(
                "description",
                ""
            )
            or ""
        ).strip()

        if not description:
            description = (
                "A control exception was "
                "identified in the evidence."
            )

        candidates.append(
            ControlClaimCandidate(
                control_id=control_id,
                statement=(
                    "Evidence contains an "
                    "identified control exception: "
                    f"{description}"
                ),
                source_reference=(
                    _source_reference(
                        evidence,
                        control_id=control_id,
                    )
                ),
                covered=None,
                tested=None,
                scope_matches=None,
                service_matches=None,
                exception_present=True,
                confidence=(
                    _normalized_confidence(
                        evidence
                    )
                ),
            )
        )

    return candidates


def _document_mapping_candidates(
    evidence,
    allowed_control_ids: set[str],
) -> list[
    ControlClaimCandidate
]:
    """
    Create possible mappings based on document type.

    These mappings are deliberately review-only because document
    presence does not prove the underlying control facts.
    """

    document_type = (
        getattr(
            evidence,
            "document_type",
            "",
        )
        or ""
    ).strip()

    candidate_controls = set()

    if (
        document_type
        in {
            "SOC 2",
            "SOC 2 Type II",
        }
    ):
        candidate_controls.update(
            {
                "GOV-01",
                "IAM-01",
                "PAM-01",
                "ENC-01",
                "SDLC-01",
                "LOG-01",
                "IR-01",
                "BCP-01",
                "TPRM-01",
                "DATA-01",
            }
        )

    elif (
        document_type
        == "Penetration Test"
    ):
        candidate_controls.update(
            {
                "VM-01",
                "SDLC-01",
            }
        )

    elif (
        document_type
        == "Incident Response Plan"
    ):
        candidate_controls.add(
            "IR-01"
        )

    elif (
        document_type
        == "BCP / DR Test"
    ):
        candidate_controls.add(
            "BCP-01"
        )

    elif (
        document_type
        == "Security Policy"
    ):
        candidate_controls.update(
            {
                "GOV-01",
                "IAM-01",
                "PAM-01",
                "DATA-01",
                "TPRM-01",
            }
        )

    elif (
        document_type
        == "Architecture Diagram"
    ):
        candidate_controls.update(
            {
                "ENC-01",
                "AI-02",
            }
        )

    candidate_controls = (
        candidate_controls
        & allowed_control_ids
    )

    candidates = []

    for control_id in sorted(
        candidate_controls
    ):

        candidates.append(
            ControlClaimCandidate(
                control_id=control_id,
                statement=(
                    f"{document_type} may contain "
                    f"evidence relevant to "
                    f"{control_id}."
                ),
                source_reference=(
                    _source_reference(
                        evidence,
                        control_id=control_id,
                    )
                ),
                covered=None,
                tested=None,
                scope_matches=None,
                service_matches=None,
                exception_present=None,
                confidence=(
                    _normalized_confidence(
                        evidence
                    )
                ),
            )
        )

    return candidates


def build_evidence_control_candidates(
    evidence,
    *,
    allowed_control_ids: Iterable[str],
) -> EvidenceClaimCandidateResult:
    """
    Convert one persisted evidence record into conservative
    evidence-to-control claim candidates.

    The adapter identifies possible relevance only.

    It intentionally does not manufacture assurance facts that
    are absent from the persisted evidence record.
    """

    allowed = {
        (
            control_id
            or ""
        ).strip().upper()
        for control_id
        in allowed_control_ids
        if (
            control_id
            and control_id.strip()
        )
    }

    candidates = []

    candidates.extend(
        _exception_candidates(
            evidence,
            allowed,
        )
    )

    existing_exception_controls = {
        item.control_id
        for item in candidates
    }

    for candidate in (
        _document_mapping_candidates(
            evidence,
            allowed,
        )
    ):
        if (
            candidate.control_id
            in existing_exception_controls
        ):
            continue

        candidates.append(
            candidate
        )

    return EvidenceClaimCandidateResult(
        evidence_id=evidence.id,
        candidates=tuple(
            candidates
        ),
    )