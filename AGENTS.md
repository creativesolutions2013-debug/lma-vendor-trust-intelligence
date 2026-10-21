# LMA engineering guidance

Mission: Assess the evidence before you ask the questions. Build an evidence-first
third-party risk platform with explainable, customer-defined security requirements.
Read README.md and docs/LMA_Vendor_Trust_Intelligence_End_to_End_Workflow.md for
product direction; target-state capabilities are not implementation claims.

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
