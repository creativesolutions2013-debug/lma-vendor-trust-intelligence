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
def test_variant_a_soc2_extraction():
    text = """
Service Organization
Northstar Cloud Systems, Inc. (Fictional)

SOC 2 Type II

Independent Auditor
Example Assurance LLP (Fictional)

Examination Period
January 1, 2026 - June 30, 2026

Report Date
August 15, 2026

Auditor Opinion
Unqualified, subject to noted exceptions

CC6.6
Quarterly access reviews are performed for privileged users.
Exception
Quarterly access review was completed 18 days late.

CC7.3
Critical security alerts are investigated within 24 hours.
Exception
Two critical alerts exceeded the 24-hour investigation target.
"""

    result = local_soc2_extraction(text)

    assert result["issuer"] == "Example Assurance LLP"
    assert result["document_date"] == "2026-08-15"
    assert result["coverage_start"] == "2026-01-01"
    assert result["coverage_end"] == "2026-06-30"
    assert result["opinion"] == "Unqualified"
    assert result["exceptions_count"] == 2
    assert result["exceptions"][0]["control_id"] == "CC6.6"
    assert result["exceptions"][1]["control_id"] == "CC7.3"
