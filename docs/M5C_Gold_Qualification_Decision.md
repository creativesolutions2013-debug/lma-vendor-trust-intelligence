# M5C scoped owner decision and proposed gold correction

**Decision recorded:** the user stated **“I accept those qualifications”** after
reviewing the proposed correction for `dr-failover-narrative`. This accepts the
two interpretations below; it does not certify all 16 labels, reviewer credentials,
independent human TPRM validation, technical facts, parser changes or a merge.

## Accepted qualifications

The unchanged source says, at **Line 6**:

```text
Switching the service took five hours, with up to ninety minutes of data loss.
```

- Five hours is **300 elapsed minutes**. Whether this duration is formal achieved
  RTO needs the start/stop and service-restoration acceptance definitions.
- “Up to ninety minutes” is a **<=90-minute bound**, not exact achieved RPO=90.
  It alone proves neither an actual result exceeding 60 minutes nor a result
  at or below 60 minutes. Clarify the actual recovered data point and what the
  reported bound means.

The explicit “Recovery exercise completed.” statement at **Line 5** still supports
an unconfirmed completion candidate. The five-hour narrative still warrants a
targeted provisional concern; accepting these qualifications does not erase it.

## Concrete proposed correction

[Versioned proposal](../benchmarks/proposals/m5c_gold_1_2_proposal.json):
`M5C-gold-correction-1.2-proposal`, status **proposed_not_active**.

| Current v1.1 annotation | Replacement if adopted |
| --- | --- |
| Exact achieved RTO=300 | Literal switch duration=300 minutes; formal RTO mapping unresolved |
| Exact achieved RPO=90 | Literal data-loss bound <=90 minutes; formal RPO mapping unresolved |
| completed=True | Retained, unconfirmed completion candidate |
| exception case attention | Retained as targeted provisional review, not a confirmed numerical breach |

Only `completed=True` remains in this case's proposed exact typed `gold` list.
The two literal observations are stored separately as qualified source assertions;
they do not introduce new production fact types or become eligible typed results.
The proposal records the original corpus/source hashes and removed annotations.
All other case sources, annotations and thresholds are outside this correction.
The retained attention label means targeted manual-review attention in this
proposal; it does not establish an eligible exact-metric adverse comparison.
That distinction requires a stated triage rubric before activation, so this
proposal is explicitly not ready to drop into the current harness.

## Version and execution boundary

Frozen **M5C-holdout-1.1** is preserved byte-for-byte. Its benchmark harness and
historical scores remain unchanged. The new proposal is not loaded by the harness,
not an active v1.2 corpus and not a recalculated baseline. No changed denominator,
accuracy increase, new safety rate, analyst-effort measurement or ROI is claimed.
The earlier AI review remains a historical record of the proposal before acceptance.

A future adoption must create a separate corpus version, state how qualified
assertions are evaluated and rerun the corresponding benchmark without relabelling
v1.1 results. Do not silently treat an exact numeric prediction as correct just
because its number matches an upper bound. Broad human TPRM validation and a
separate development corpus remain prerequisites for extractor work under Issue #28.

**Smallest source follow-up:** request failover start/restoration acceptance times
and actual recovery-point timestamps, then clarify the ninety-minute wording.
No vendor/control/risk approval, parser change or merge follows from this decision.
