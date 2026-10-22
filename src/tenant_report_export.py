"""M4C-2B-2A: bounded, unwired, tenant-scoped report export.

Not connected to legacy Streamlit Reports, a browser, or real SSO. The caller
MUST use a server-injected identity source backed by a valid current session.
The sole authority is the fresh database membership + per-engagement grants
checked by TenantReadService, not caller-selected vendor ids or a role DTO.

No evidence bytes, storage keys, scores, governed decisions, or report writes.
"""
from dataclasses import dataclass
import csv
from io import StringIO

from src.authz import PERMISSION_REPORT_EXPORT
from src.tenant_read_scope import TenantReadService, _session_identity_key


@dataclass(frozen=True)
class ScopedReportRow:
    vendor_id: int
    vendor_name: str
    engagement_id: int
    service_name: str
    assessments: int
    evidence_items: int


@dataclass(frozen=True)
class ScopedReport:
    rows: tuple[ScopedReportRow, ...]
    csv_bytes: bytes


def _same_authority(first, second):
    return (first is not None and second is not None
            and _session_identity_key(first.identity) == _session_identity_key(second.identity)
            and first.role == second.role
            and first.engagement_ids == second.engagement_ids)


def _safe_csv_cell(value):
    """Guard spreadsheet formula execution from untrusted vendor/service labels."""
    if type(value) is not str:
        return value
    # Prefix apostrophe before any leading whitespace/control + formula prefix.
    # Include plain leading tabs/newlines, which may confuse CSV consumers.
    prefix = value.lstrip(" \t\r\n")
    if value[:1] in ("\t", "\r", "\n") or prefix.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


class TenantReportService:
    """Read-only report for *explicitly granted* engagement relationships.

    Missing, revoked, expired or changed session/grant/role produces no report.
    Metadata is checked twice, then authorization and the current server session
    are checked after CSV preparation. A future API must still use a secure
    transport and record authorized export audits independently.
    """

    def __init__(self, session_factory, *, identity_source=None):
        self._reader = TenantReadService(session_factory, identity_source=identity_source)

    def _data(self, scope):
        reader = self._reader
        vendors = reader._project("vendor", scope)
        engagements = reader._project("engagement", scope)
        assessments = reader._project("assessment", scope)
        evidence = reader._project("evidence", scope)
        return vendors, engagements, assessments, evidence

    @staticmethod
    def _rows(data):
        vendors, engagements, assessments, evidence = data
        vendor_by_id = {v.id: v for v in vendors}
        assessment_counts = {}
        for item in assessments:
            assessment_counts[item.engagement_id] = assessment_counts.get(item.engagement_id, 0) + 1
        evidence_counts = {}
        for item in evidence:
            evidence_counts[item.engagement_id] = evidence_counts.get(item.engagement_id, 0) + 1
        result = []
        for engagement in engagements:
            vendor = vendor_by_id.get(engagement.vendor_id)
            if vendor is None:
                # No incomplete/cross-linked partial report is acceptable.
                return None
            result.append(ScopedReportRow(
                vendor_id=vendor.id,
                vendor_name=vendor.display_name,
                engagement_id=engagement.id,
                service_name=engagement.service_name,
                assessments=assessment_counts.get(engagement.id, 0),
                evidence_items=evidence_counts.get(engagement.id, 0),
            ))
        return tuple(result)

    @staticmethod
    def _csv(rows):
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(("Vendor ID", "Vendor", "Engagement ID", "Service",
                         "Assessments", "Evidence Items"))
        for row in rows:
            writer.writerow((
                row.vendor_id, _safe_csv_cell(row.vendor_name),
                row.engagement_id, _safe_csv_cell(row.service_name),
                row.assessments, row.evidence_items,
            ))
        return output.getvalue().encode("utf-8")

    def build(self) -> ScopedReport | None:
        try:
            reader = self._reader
            first = reader._scope(PERMISSION_REPORT_EXPORT)
            if first is None or not first.engagement_ids:
                return None
            data = self._data(first)
            second = reader._scope(PERMISSION_REPORT_EXPORT)
            if not _same_authority(first, second) or data != self._data(second):
                return None
            rows = self._rows(data)
            if not rows:
                return None
            csv_bytes = self._csv(rows)
            # Revalidate after assembling bytes, including effects of DB work
            # and access expiry; never return stale scope after revocation.
            final = reader._scope(PERMISSION_REPORT_EXPORT)
            if not _same_authority(first, final):
                return None
            current = reader._identity_source.authenticated_identity()
            if (type(current) is not type(final.identity)
                    or _session_identity_key(current) != _session_identity_key(final.identity)):
                return None
            # Scope's time/DB checks run in _scope; explicit final time check.
            from src.tenant_read_scope import _current, _utc_now
            if not _current(current.issued_at, current.expires_at, _utc_now()):
                return None
            return ScopedReport(rows, csv_bytes)
        except Exception:
            # Same external behavior as no entitlement. No database, token, or
            # provider diagnostics leak through this surface.
            return None
