from dataclasses import dataclass


@dataclass(frozen=True)
class TargetedReviewScope:
    affected_domain: str
    review_controls: tuple[str, ...]
    request_evidence: tuple[str, ...]
    reusable_evidence: tuple[str, ...]
    excluded_domains: tuple[str, ...]
    rationale: str


_COMMON_EXCLUSIONS = (
    "Physical security",
    "Personnel security",
)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def build_targeted_review_scope(
    *,
    affected_domain: str,
    event_type: str,
    tier_code: str,
    ai_enabled: bool = False,
    regulated_data: bool = False,
) -> TargetedReviewScope:

    domain = _norm(affected_domain)
    event = _norm(event_type)

    # -----------------------------------------------------
    # External security posture / vulnerability change
    # -----------------------------------------------------

    if domain == "external security posture":
        controls = [
            "Vulnerability and patch management",
            "External attack surface management",
            "Security monitoring",
        ]

        evidence = [
            "Current vulnerability remediation evidence",
            "Latest penetration test status or report",
            "Patch / remediation SLA evidence",
        ]

        reusable = [
            "Current SOC 2 Type II or equivalent assurance report",
            "Current Security Policy",
        ]

        exclusions = [
            "Business continuity and disaster recovery",
            "Privacy governance",
            "Physical security",
            "Personnel security",
        ]

        if event == "critical kev exposure":
            evidence.append(
                "KEV exposure remediation or compensating-control evidence"
            )

        return TargetedReviewScope(
            affected_domain=affected_domain,
            review_controls=tuple(controls),
            request_evidence=tuple(evidence),
            reusable_evidence=tuple(reusable),
            excluded_domains=tuple(exclusions),
            rationale=(
                "The signal concerns vulnerability or external security "
                "posture. Review should stay focused on exposure, patching, "
                "remediation, and monitoring rather than reopening unrelated "
                "control domains."
            ),
        )

    # -----------------------------------------------------
    # Security incident
    # -----------------------------------------------------

    if domain == "security incident":
        controls = [
            "Incident response",
            "Logging and monitoring",
            "Identity and access management",
            "Vulnerability management",
        ]

        evidence = [
            "Incident summary and timeline",
            "Root cause analysis",
            "Containment and remediation evidence",
            "Relevant incident response records",
        ]

        reusable = [
            "Current Incident Response Plan",
            "Current SOC 2 Type II or equivalent assurance report",
        ]

        exclusions = [
            "Business continuity and disaster recovery",
            "Physical security",
            "Personnel security",
        ]

        if event == "credential exposure":
            evidence += [
                "Credential reset / revocation evidence",
                "MFA and privileged-access validation",
            ]

        if event == "ransomware event":
            controls += [
                "Backup and recovery",
                "Business continuity",
            ]
            evidence += [
                "Recovery validation",
                "Backup restoration evidence",
            ]
            exclusions = [
                item
                for item in exclusions
                if item
                != "Business continuity and disaster recovery"
            ]

        return TargetedReviewScope(
            affected_domain=affected_domain,
            review_controls=tuple(dict.fromkeys(controls)),
            request_evidence=tuple(dict.fromkeys(evidence)),
            reusable_evidence=tuple(reusable),
            excluded_domains=tuple(exclusions),
            rationale=(
                "The review is limited to the incident, affected security "
                "controls, containment, root cause, and remediation. A full "
                "vendor reassessment is not justified unless the incident "
                "reveals broader control failure."
            ),
        )

    # -----------------------------------------------------
    # AI / service change
    # -----------------------------------------------------

    if domain == "ai / service change":
        controls = [
            "AI governance and model accountability",
            "AI data handling and model access controls",
            "AI change, evaluation, and incident management",
            "Data protection and retention",
            "Third- and fourth-party risk management",
        ]

        evidence = [
            "Updated AI architecture or data-flow documentation",
            "AI governance / acceptable use documentation",
            "Model or AI service change description",
            "AI subprocessor / model provider inventory",
            "Data-use and retention documentation",
        ]

        reusable = [
            "Current SOC 2 Type II or equivalent assurance report",
            "Current Security Policy",
        ]

        if regulated_data:
            controls += [
                "Regulated data handling and minimization",
                "Data retention and secure disposal",
            ]
            evidence += [
                "Applicable regulatory assurance evidence",
            ]

        return TargetedReviewScope(
            affected_domain=affected_domain,
            review_controls=tuple(dict.fromkeys(controls)),
            request_evidence=tuple(dict.fromkeys(evidence)),
            reusable_evidence=tuple(reusable),
            excluded_domains=(
                "Business continuity and disaster recovery",
                "Physical security",
                "Personnel security",
            ),
            rationale=(
                "The service change introduces or alters AI capability. "
                "Review should focus on AI governance, data use, model access, "
                "subprocessors, retention, and architecture instead of "
                "repeating the full security assessment."
            ),
        )

    # -----------------------------------------------------
    # Service / architecture change
    # -----------------------------------------------------

    if domain == "service / architecture":
        controls = [
            "Architecture and security boundaries",
            "Identity and access management",
            "Encryption and data protection",
            "Logging and monitoring",
            "Third- and fourth-party risk management",
        ]

        evidence = [
            "Updated architecture diagram",
            "Updated data-flow diagram",
            "Material change description",
            "Relevant access-control evidence",
        ]

        reusable = [
            "Current SOC 2 Type II or equivalent assurance report",
            "Current Security Policy",
        ]

        return TargetedReviewScope(
            affected_domain=affected_domain,
            review_controls=tuple(controls),
            request_evidence=tuple(evidence),
            reusable_evidence=tuple(reusable),
            excluded_domains=(
                "Business continuity and disaster recovery",
                "Physical security",
                "Personnel security",
            ),
            rationale=(
                "The vendor changed service or architecture. Review should "
                "validate changed boundaries, data flows, access, encryption, "
                "logging, and dependencies without reopening unaffected areas."
            ),
        )

    # -----------------------------------------------------
    # Assurance evidence expiration
    # -----------------------------------------------------

    if domain == "assurance evidence":
        return TargetedReviewScope(
            affected_domain=affected_domain,
            review_controls=(),
            request_evidence=(
                "Replacement or renewed assurance evidence",
            ),
            reusable_evidence=(
                "All other current evidence remains reusable",
            ),
            excluded_domains=(
                "Identity and access management",
                "Business continuity and disaster recovery",
                "Vulnerability management",
                "Incident response",
                "Physical security",
                "Personnel security",
            ),
            rationale=(
                "Evidence freshness alone should not reopen unrelated "
                "controls. Replace the expired artifact first and expand "
                "scope only if the new evidence reveals material issues."
            ),
        )

    # -----------------------------------------------------
    # Generic fallback
    # -----------------------------------------------------

    controls = [
        "Security governance and ownership",
        "Relevant changed control area",
    ]

    evidence = [
        "Evidence supporting the reported material change",
    ]

    if tier_code == "T1":
        evidence.append(
            "Current assurance evidence supporting the affected control"
        )

    if ai_enabled:
        controls.append(
            "AI governance and model accountability"
        )

    return TargetedReviewScope(
        affected_domain=affected_domain or "General",
        review_controls=tuple(dict.fromkeys(controls)),
        request_evidence=tuple(dict.fromkeys(evidence)),
        reusable_evidence=(
            "Current evidence outside the changed risk domain",
        ),
        excluded_domains=_COMMON_EXCLUSIONS,
        rationale=(
            "The changed domain is not specifically mapped yet. "
            "Use a narrowly scoped review of the reported change and "
            "expand only when evidence identifies broader control impact."
        ),
    )
