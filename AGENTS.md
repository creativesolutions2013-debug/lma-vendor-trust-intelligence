# LMA engineering guidance

Mission: Assess the evidence before you ask the questions. Build an evidence-first
third-party risk platform with explainable, customer-defined security requirements.
Read README.md and docs/LMA_Vendor_Trust_Intelligence_End_to_End_Workflow.md for
product direction; target-state capabilities are not implementation claims.

## Cross-control product invariant

The platform capability is **Evidence-Based Control Assurance** across every
applicable customer requirement, not an MFA evaluation engine. Privileged MFA
is an initial **reference example**, never the product or architecture boundary.
Every control must ultimately be evaluated against its customer-defined,
versioned acceptance threshold and applicable standards, using source-verifiable
facts, relevant technical implementation, enforcement/coverage, operating proof,
service/population scope, age, exceptions and uncertainty. Not all controls use
the same technical tests: keep a small shared assurance/review contract with
control-specific evaluators. A citation, framework label or claim that a control
exists is never sufficient proof of meeting the requirement. Do not relabel an
MFA-only pilot as a generalized implementation. Prove shared behavior with
at least two genuinely non-MFA control families before claiming reusable
cross-control support. See GitHub issue #5 for M3D acceptance criteria.
The same evidence and analyst-review lifecycle must accept every applicable
customer-defined requirement independently of specialist evaluator availability.
Families are registered from applicable review cases, never a platform whitelist.
Without specialist rules, retain the requirement, citations, concerns and review
history; disclose the limitation and return provisional Needs Review with usable
evidence or Evidence Missing without it. Never infer passing, failure or compliance.
Fallback suitability requires versioned requirement-specific evidence expectations
and explicit source relevance. A policy may serve documented governance; it never
proves technical operating effectiveness merely by being accepted for review.
The synthetic proof and its limits are documented in
docs/M3D_Evidence_Based_Control_Assurance.md. Workflow coverage is extensible;
automated technical coverage remains limited to tested domain evaluators.

- Work on a dedicated feature branch based on current main. Preserve existing work;
  never modify or push directly to main. Merge/publish only when authorized.
- Never inspect or expose secrets or confidential vendor evidence. Use synthetic
  fixtures. No real AI calls without explicit authorization for that task/data.
- Do not change databases or authentication unless explicitly in scope. Test with
  isolated in-memory databases; never run destructive smoke tests on real data.
- AI/evaluators propose; authorized humans confirm. Preserve exact citations,
  uncertainty, adverse evidence, policy versions, and historical control meanings.
  Missing evidence is not control failure. Subrequirement support is not whole-
  control approval. Draft results must not change governed claims, dispositions,
  authoritative risk calculations, or approvals automatically.
- Keep changes small. Avoid new dashboards, generic policy engines, and unnecessary
  forms. Do not expand scope beyond the user's authorization.
- Add meaningful synthetic regressions for evaluator changes. Compile app.py and
  touched Python modules; run the full pytest suite with DATABASE_URL=sqlite:///:memory:
  and no real AI/network calls. Review git diff --check and the complete diff.
  Report results, skipped checks, limitations, and remaining security risks.
