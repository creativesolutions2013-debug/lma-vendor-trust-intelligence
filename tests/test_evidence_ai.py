from src.evidence_ai import local_soc2_extraction


def test_variant_b_soc2_extraction():
    text = """
Organization
Redwood Data Services LLC (Fictional)

Assurance report
SOC 2 Type II

Independent service auditor
Fictional Controls & Assurance CPAs

Period under examination
02/01/2026 through 07/31/2026

Report issued
September 12, 2026

Conclusion
Unmodified opinion with one noted testing exception

CC6.2
Privileged access is approved and reviewed on a recurring basis.
Passed
No exceptions identified.

CC7.1
Security monitoring alerts are triaged according to documented procedures.
Exception noted
One high-severity alert was reviewed 36 hours after creation, exceeding the 24-hour target.

A1.1
Capacity and availability are monitored against defined thresholds.
Passed
No exceptions identified.
"""

    result = local_soc2_extraction(text)

    assert result["issuer"] == "Fictional Controls & Assurance CPAs"
    assert result["document_date"] == "2026-09-12"
    assert result["coverage_start"] == "2026-02-01"
    assert result["coverage_end"] == "2026-07-31"
    assert result["opinion"] == "Unmodified"
    assert result["exceptions_count"] == 1
    assert result["exceptions"][0]["control_id"] == "CC7.1"
    assert "36 hours after creation" in result["exceptions"][0]["description"]
