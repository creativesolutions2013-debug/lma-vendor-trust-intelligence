"""MFA adapter into the neutral presentation contract; M3B/C gates stay intact."""
from src.control_assurance_presentation import AssurancePresentation, Attention, CitedInterpretation


def mfa_review_family():
    """Explicit compatibility debt: legacy actions still use their original UI."""
    from src.control_assurance_registry import ReviewFamily
    from src.mfa_review_pilot import pilot_cases

    def render(*, actor_label):
        from src.mfa_review_ui import render_mfa_review_pilot
        render_mfa_review_pilot(actor_label=actor_label)

    return ReviewFamily("Privileged MFA", pilot_cases(), render, ("m3c1_current_review",))


def present_mfa(case, view):
    r = case.requirement
    attention = []
    prominent = [i for i in view.issues if i.priority <= 2]
    secondary = [i for i in view.issues if i.priority > 2]
    for i in prominent or secondary[:1]:
        attention.append(Attention(i.title, i.detail, tuple(
            CitedInterpretation("", c.filename, c.location, c.quote, "", False) for c in i.citations)))
    return AssurancePresentation(
        r.requirement_id, "Privileged administrator MFA",
        f"{r.customer_policy_id} v{r.version}. {r.service} · {r.environment} · {r.account_scope}.",
        "enforced MFA for the complete administrator population; "
        f"allowed methods: {', '.join(r.allowed_methods).upper()}; "
        f"phishing resistance {'required' if r.phishing_resistant else 'not required'}; "
        f"operating tests {'required' if r.require_operating else 'not required'}; "
        f"evidence no older than {r.max_age_days} days. "
        "All fallback and recovery paths must meet the same threshold.",
        view.validation.evaluation.outcome, tuple(attention), tuple(
            CitedInterpretation(f.statement, f.filename, f.location, f.quote, f.fingerprint, f.confirmed)
            for f in view.supporting),
        f"{sum(f.status != 'validated' for f in view.validation.facts)} interpretation(s) remain unconfirmed or unsupported; "
        f"{sum(s.status == 'needs_review' for s in view.validation.signals)} source signal(s) remain unresolved in the validated bundle. "
        "Matching quotations alone do not establish correct meaning or control operation. "
        "Source hashes establish consistency, not authenticity.", view.next_action,
    )
