"""Small synthetic analyst workspace over the authorized custody/revision APIs.

The HTTP adapter owns browser authentication, CSRF and response policy. This
module accepts only its server-injected identity dependencies and a fixed SQL
assessment. It never persists browser objects or writes SQL directly.
"""
from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256
from html import escape
import re

from src.guided_assessment_demo import ACTIONS
from src.organization_methodology import OrganizationMethodology
from src.resumable_assessment import ResumedAssessment, SyntheticResumableAssessmentService
from src.resumable_assessment_state import encode_draft
from src.session_identity_source import SessionIdentitySource
from src.synthetic_evidence_custody import SyntheticEvidenceCustodyService
from src.tenant_read_scope import TenantReadService
from src.upload_assessment import (
    CRITICALITY_POINTS, SYSTEM_ACCESS_POINTS, Intake, build_assessment,
    read_upload, risk_and_applicability,
)


MAX_FILES = 4
MAX_FILE_BYTES = 65536
MAX_TOTAL_BYTES = MAX_FILES * MAX_FILE_BYTES
ALL_APPLICABLE = "All applicable"
KINDS = ("policy", "assertion", "configuration", "test")
_SAVE_FIELDS = {"use_case", "data", "access", "criticality", "kind", "requirement_id", "observed_on"}
_REVIEW_FIELDS = {"requirement_id", "action", "rationale", "confirms_insufficiency"}


def _revision(value, *, initial=False):
    return type(value) is int and (0 if initial else 1) <= value < 2**31 - 1


def _fields(values, allowed):
    if (type(values) is not dict or not set(values) <= allowed
            or any(type(value) is not str for value in values.values())):
        raise ValueError("Unsupported workspace fields.")


def _today(identity):
    now = identity.clock()
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Use the trusted server UTC clock.")
    return now.astimezone(timezone.utc).date()


class PilotWorkspace:
    """One fixed, server-provisioned synthetic assessment; no generic CRUD."""

    def __init__(self, factory, intake):
        if (not callable(factory) or type(intake) is not Intake
                or type(intake.methodology) is not OrganizationMethodology
                or re.fullmatch(r"[1-9][0-9]{0,18}", intake.assessment_id) is None
                or int(intake.assessment_id) > 2**63 - 1):
            raise ValueError("Use a fixed synthetic SQL assessment and methodology.")
        self._factory = factory
        self._intake = intake
        self._assessment_id = int(intake.assessment_id)

    @property
    def intake(self):
        return self._intake

    def _source(self, handle, identity):
        return SessionIdentitySource(identity.sessions, handle, self._factory, clock=identity.clock)

    def _service(self, handle, identity):
        return SyntheticResumableAssessmentService(
            self._factory, identity_source=self._source(handle, identity))

    def available(self, handle, identity):
        """A fresh scope check for an empty workspace; never byte authority."""
        try:
            result = TenantReadService(self._factory, identity_source=self._source(handle, identity)).get_assessment(
                self._assessment_id)
            return result is not None and result.id == self._assessment_id
        except Exception:
            return False

    def resume(self, handle, identity):
        try:
            return self._service(handle, identity).resume(self._assessment_id)
        except Exception:
            return None

    def save(self, handle, identity, expected_revision, fields, files):
        """Save a complete replacement inventory, after validating every file.

        Originals are staged separately from the revision append. An intervening
        failure/race may leave immutable unattached originals or an unacknowledged
        commit; False does not promise rollback. Never automatically retry it.
        """
        try:
            if not _revision(expected_revision, initial=True):
                return False
            _fields(fields, _SAVE_FIELDS)
            if type(files) is not tuple or not 1 <= len(files) <= MAX_FILES:
                return False
            names, hashes, total = set(), set(), 0
            for item in files:
                if type(item) is not tuple or len(item) != 2:
                    return False
                name, content = item
                if (type(name) is not str or name != name.strip()
                        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}", name) is None
                        or not name.lower().endswith(".txt") or name in names
                        or type(content) is not bytes or not 1 <= len(content) <= MAX_FILE_BYTES):
                    return False
                digest = sha256(content).hexdigest()
                if digest in hashes:
                    return False
                names.add(name)
                hashes.add(digest)
                total += len(content)
            if total > MAX_TOTAL_BYTES:
                return False

            # This catches ordinary stale form submissions before staging any
            # originals. The revision service still owns the final atomic CAS.
            current = self.resume(handle, identity)
            if current is not None:
                if current.revision != expected_revision:
                    return False
            elif expected_revision != 0 or not self.available(handle, identity):
                return False

            base = current.intake if current is not None else self._intake
            values = {name: fields.get(name, getattr(base, name))
                      for name in ("use_case", "data", "access", "criticality")}
            intake = replace(base, **values, as_of=_today(identity),
                assessment_id=self._intake.assessment_id, vendor=self._intake.vendor,
                service=self._intake.service, environment=self._intake.environment,
                organization_id=self._intake.organization_id, methodology=base.methodology)
            kind = fields.get("kind", "policy")
            if kind not in KINDS:
                return False
            raw_date = fields.get("observed_on", "")
            if raw_date:
                if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_date) is None:
                    return False
                observed_on = date.fromisoformat(raw_date)
                if observed_on > intake.as_of:
                    return False
            else:
                observed_on = None
            applicable = tuple(control.control_id for control in risk_and_applicability(intake)[2].controls)
            selected = fields.get("requirement_id", "BCP-01" if "BCP-01" in applicable else ALL_APPLICABLE)
            if selected == ALL_APPLICABLE:
                targets = applicable
            elif selected in applicable:
                targets = (selected,)
            else:
                return False

            uploads = tuple(read_upload(intake, name, content, targets, kind=kind,
                observed_on=observed_on, service=intake.service, environment=intake.environment)
                for name, content in files)
            build_assessment(intake, uploads)
            # All request fields, names and original text have passed the native
            # validators before the first immutable custody insertion.
            custody = SyntheticEvidenceCustodyService(
                self._factory, identity_source=self._source(handle, identity))
            receipts, captured_uploads = [], []
            for (name, content), upload in zip(files, uploads):
                receipt = custody.save(self._assessment_id, content, document_name=name)
                if receipt is None:
                    return False
                captured = receipt.created_at.astimezone(timezone.utc).date()
                receipts.append(receipt)
                # A midnight crossing must retain the actual custody date,
                # rather than the earlier request/prevalidation date.
                captured_uploads.append(upload if captured == intake.as_of else read_upload(
                    replace(intake, as_of=captured), name, content, targets, kind=kind,
                    observed_on=observed_on, service=intake.service, environment=intake.environment))
            intake = replace(intake, as_of=max(intake.as_of, *(r.created_at.astimezone(timezone.utc).date()
                                                           for r in receipts)))
            draft = encode_draft(intake, tuple(captured_uploads), tuple(receipts))
            return self._service(handle, identity).save(self._assessment_id,
                expected_revision=expected_revision, draft=draft) is not None
        except Exception:
            return False

    def review(self, handle, identity, revision, fields):
        try:
            if not _revision(revision):
                return False
            _fields(fields, _REVIEW_FIELDS)
            requirement_id, action, rationale = (fields.get(name, "")
                                                for name in ("requirement_id", "action", "rationale"))
            confirmation = fields.get("confirms_insufficiency", "")
            if (not 1 <= len(requirement_id) <= 80 or action not in ACTIONS
                    or not 1 <= len(rationale) <= 1200 or not rationale.strip()
                    or confirmation not in ("", "yes")):
                return False
            return self._service(handle, identity).record_review(self._assessment_id,
                expected_revision=revision, requirement_id=requirement_id, action=action,
                rationale=rationale, confirms_insufficiency=confirmation == "yes") is not None
        except Exception:
            return False

    def finish(self, handle, identity, revision):
        try:
            return (_revision(revision) and self._service(handle, identity).finish(
                self._assessment_id, expected_revision=revision) is not None)
        except Exception:
            return False

    def capture_vendor_submission(self, handle, identity, revision, handoff, invitation_id):
        # Serialize revocation with the entire capture/import outcome. Individual
        # queue lookups cannot authorize a later append after pending intake was
        # revoked. Queue locks precede SQL/session authority on every queue path.
        try:
            with handoff.capture_operation(handle, identity, invitation_id) as allowed:
                return bool(allowed and self._capture_vendor_submission(
                    handle, identity, revision, handoff, invitation_id))
        except Exception:
            return False

    def _capture_vendor_submission(self, handle, identity, revision, handoff, invitation_id):
        """Explicit analyst capture, then append; never substitute vendor authority.

        An uncertain custody acknowledgment is terminal. A confirmed custody
        receipt may be reused after an append conflict, never staged a second time.
        """
        try:
            if not _revision(revision):
                return False
            current = self.resume(handle, identity)
            if current is None or current.revision != revision:
                return False
            pending = handoff.get_pending(handle, identity, invitation_id)
            if pending is None:
                return False
            if (len(current.uploads) >= MAX_FILES or any(
                    upload.evidence.source.filename == pending.filename
                    or upload.evidence.content_sha256 == pending.sha256 for upload in current.uploads)):
                # A lost append acknowledgment is recovered from verified latest state.
                return self._recover_vendor_append(handle, identity, handoff, invitation_id, pending.receipt)
            if pending.receipt is None:
                pending = handoff.begin_capture(handle, identity, invitation_id)
                if pending is None:
                    return False
                custody = SyntheticEvidenceCustodyService(self._factory, identity_source=self._source(handle, identity))
                receipt = custody.save(self._assessment_id, pending.content, document_name=pending.filename)
                if receipt is None:
                    handoff.mark_unconfirmed(handle, identity, invitation_id)
                    return False
                if not handoff.record_capture(handle, identity, invitation_id, receipt):
                    handoff.mark_unconfirmed(handle, identity, invitation_id)
                    return False
            else:
                receipt = pending.receipt
            metadata = {
                "schema_version": 1, "invitation_id": pending.invitation_id,
                "vendor_issuer": pending.vendor_issuer, "vendor_subject": pending.vendor_subject,
                "vendor_session_id": pending.vendor_session_id,
                "vendor_role": "Authenticated synthetic invitee",
                "submitted_at": pending.submitted_at.isoformat(),
                "kind": pending.kind,
                "observed_on": pending.observed_on.isoformat() if pending.observed_on else None,
                "requirement_id": pending.requirement_id,
                "inviter_issuer": pending.inviter_issuer, "inviter_subject": pending.inviter_subject,
                "inviter_session_id": pending.inviter_session_id,
            }
            saved = self._service(handle, identity).append_vendor_source(self._assessment_id,
                expected_revision=revision, receipt=receipt, metadata=metadata)
            if saved is not None:
                return handoff.mark_imported(handle, identity, invitation_id)
            return self._recover_vendor_append(handle, identity, handoff, invitation_id, receipt)
        except Exception:
            # A caller can only retry a confirmed captured receipt. Capturing
            # without an acknowledgment is never converted back to submitted.
            return False

    def _recover_vendor_append(self, handle, identity, handoff, invitation_id, receipt):
        if receipt is None:
            return False
        latest = self.resume(handle, identity)
        if latest is None:
            return False
        for source in latest.report.get("persistence", {}).get("source_custody", []):
            if (source["evidence_id"] == receipt.evidence_id and source["generation"] == receipt.generation
                    and source["sha256"] == receipt.sha256
                    and (source.get("vendor_delivery") or {}).get("invitation_id") == invitation_id):
                return handoff.mark_imported(handle, identity, invitation_id)
        return False

    def render_vendor_handoff(self, handle, identity, result, handoff):
        """Analyst-only controls; public correlation IDs confer no authority."""
        e = lambda value: escape(str(value), quote=True)
        csrf = identity.csrf_token(handle)
        summaries = handoff.list_invitations(handle, identity)
        if summaries is None:
            return '<p>Vendor handoff unavailable for this session.</p>'
        hidden = (f'<input type="hidden" name="csrf" value="{e(csrf)}">'
                  f'<input type="hidden" name="expected_revision" value="{result.revision}">')
        options = ''.join(f'<option value="{e(row["requirement_id"])}">{e(row["requirement_id"])}</option>'
                          for row in result.report['requirements'])
        parts = ['<section><h2>Request evidence from the synthetic vendor</h2>',
            '<p>One local invitation and one TXT source. Keep this analyst session signed in until delivery. '
            'Vendor delivery is pending in memory until you explicitly capture it below. '
            'No external message or vendor decision is created.</p>',
            f'<form method="post" action="/vendor-invitation/create">{hidden}'
            f'<label>Requirement <select name="requirement_id">{options}</select></label>'
            '<button>Create local vendor invitation</button></form>']
        for summary in summaries:
            parts.append(f'<article><p>Invitation {e(summary.invitation_id)} · {e(summary.status)} '
                         f'· expires {e(summary.expires_at.isoformat())}</p>')
            public_id = f'<input type="hidden" name="invitation_id" value="{e(summary.invitation_id)}">'
            if summary.status in ('submitted', 'captured'):
                parts.append(f'<form method="post" action="/vendor-invitation/capture">{hidden}{public_id}'
                             '<button>Capture vendor evidence and reassess</button></form>')
            if summary.status in ('issued', 'submitted', 'captured'):
                parts.append(f'<form method="post" action="/vendor-invitation/revoke">'
                    f'<input type="hidden" name="csrf" value="{e(csrf)}">{public_id}'
                    '<button>Revoke invitation or pending intake</button></form>')
            parts.append('</article>')
        parts.append('</section>')
        return ''.join(parts)


def render_workspace(intake, result, csrf):
    """Render escaped server-rebuilt data; returned markup is no authorization."""
    if type(intake) is not Intake or (result is not None and type(result) is not ResumedAssessment):
        raise ValueError("Use the current server workspace result.")
    e = lambda value: escape(str(value), quote=True)
    current = result.intake if result is not None else intake
    revision = result.revision if result is not None else 0
    policy = current.methodology.definition
    controls = risk_and_applicability(current)[2].controls
    targets = [(ALL_APPLICABLE, ALL_APPLICABLE)] + [(c.control_id, c.control_id + " · " + c.requirement)
                                                  for c in controls]
    default_target = "BCP-01" if any(c.control_id == "BCP-01" for c in controls) else ALL_APPLICABLE

    def hidden(*, with_revision=True):
        return (f'<input type="hidden" name="csrf" value="{e(csrf)}">'
                + (f'<input type="hidden" name="expected_revision" value="{revision}">' if with_revision else ""))

    def select(name, label, options, selected):
        values = [(item, item) if type(item) is str else item for item in options]
        return (f'<label>{e(label)} <select name="{e(name)}">' + "".join(
            f'<option value="{e(value)}"' + (' selected' if value == selected else '') + f'>{e(title)}</option>'
            for value, title in values) + '</select></label>')

    parts = ['<p>Development pilot · synthetic TXT documents only. Results remain provisional; '
        'missing evidence is not control failure. No vendor approval or risk acceptance is created.</p>',
        f'<p><strong>{e(current.vendor)}</strong> · {e(current.service)} · {e(current.environment)}</p>',
        f'<p>Organization: {e(current.organization_id)} · Methodology: {e(policy["name"])} '
        f'v{e(policy["version"])} · Assessment {e(current.assessment_id)}</p>',
        f'<form method="post" action="/logout">{hidden(with_revision=False)}'
        '<button type="submit">Sign out</button></form>']
    if result is not None:
        parts.append('<details><summary>Update context or replace evidence</summary>')
    parts.extend([
        '<h2>Attach evidence and save</h2>',
        '<p>Select 1–4 UTF-8 TXT files, up to 64 KiB each and 256 KiB total. '
        'All files use the assessed service and environment as uploader-declared scope. '
        'Document kind, observation date and requirement routing are declarations, not verified facts.</p>'])
    if result is not None:
        parts.append('<p>Select every file that should remain attached. Saving replaces the complete current file selection; '
                     'earlier review history remains and may require re-review.</p>')
    parts.extend([f'<form method="post" action="/save" enctype="multipart/form-data">{hidden()}',
        f'<label>Business use case <input name="use_case" maxlength="500" required value="{e(current.use_case)}"></label>',
        select('data', 'Data sensitivity', ('Public', 'Confidential', 'Restricted'), current.data),
        select('access', 'System access', tuple(SYSTEM_ACCESS_POINTS), current.access),
        select('criticality', 'Business criticality', tuple(CRITICALITY_POINTS), current.criticality),
        '<label>Synthetic evidence <input type="file" name="files" accept=".txt,text/plain" multiple required></label>',
        select('requirement_id', 'Related requirement (routing only)', targets, default_target),
        select('kind', 'Document kind', KINDS, 'policy'),
        '<label>Observation or test date, if known <input type="date" name="observed_on"></label>',
        '<button type="submit">Save evidence and evaluate</button></form>'])
    if result is not None:
        parts.append('</details>')
    if result is None:
        parts.append('<p>No saved revision could be resumed. For a new assessment, attach a synthetic document to begin. '
                     'If you previously saved, sign out and sign in again to retry resume before submitting more files. '
                     'An unavailable revision does not imply that an earlier save was rolled back.</p>')
        return "\n".join(parts)

    report = result.report
    parts.extend([f'<h2>Saved assessment · revision {revision}</h2>',
        f'<p>State contract v1 · Current evaluation date: {e(report["scope"]["as_of"])} · '
        f'{e(report["review_completion"]["status"])}</p>',
        f'<details><summary>Saved state fingerprint</summary><code>{e(result.state_sha256)}</code></details>'])
    if result.completion_stale:
        parts.append('<p role="status">Earlier completion is stale. Review the changed context and explicitly finish again.</p>')
    parts.append('<h3>Current original evidence</h3><ul>')
    for upload in result.uploads:
        source = upload.evidence.source
        parts.append(f'<li>{e(source.filename)} · {e(source.evidence_kind)} · observed {e(source.observed_on)} '
                     f'· captured {e(source.captured_on)} · {e(source.service)} / {e(source.environment)}</li>')
    for source in report.get('persistence', {}).get('source_custody', []):
        parts.append(f'<li>{e(source["filename"])} · original SHA-256 {e(source["sha256"])} '
                     f'· custody capture actor {e(source["capture_actor"]["subject"])}</li>')
        if source.get('vendor_delivery'):
            delivery = source['vendor_delivery']
            parts.append(f'<li>Authenticated synthetic vendor delivery: {e(delivery["vendor_subject"])} '
                         f'· delivered {e(delivery["submitted_at"])} · declaration: {e(delivery["kind"])} '
                         '· unverified source claims, separately captured by the analyst.</li>')
    parts.append('</ul><h2>Requirements and source review</h2>')
    for row in report['requirements']:
        opened = ' open' if row['requirement_id'] == default_target else ''
        parts.extend([f'<details{opened}><summary>{e(row["requirement_id"])} · {e(row["outcome"])} '
            f'· {e(row["title"])}</summary><article>',
            f'<p><strong>{e(row["outcome"])}</strong> · Provisional</p>',
            f'<p>Customer threshold: {e(row["threshold_summary"])}</p>'])
        presentation = row.get('presentation') or {}
        if presentation.get('uncertainty'):
            parts.append(f'<p>{e(presentation["uncertainty"])}</p>')
        for attention in presentation.get('attention', []):
            parts.append(f'<p><strong>{e(attention["title"])}</strong>: {e(attention["detail"])}</p>')
        for need in row['needs']:
            parts.append(f'<p>{e(need["status"])}: {e(need["rationale"])} '
                         f'Needed: {e(need["missing_fact"])} · Acceptable evidence: {e(need["acceptable_evidence"])}</p>')
        for citation in row['citations'] + row['customer_policy_citations']:
            parts.append(f'<details><summary>{e(citation["filename"])} · {e(citation["location"])}</summary>'
                         f'<p>{e(citation["evidence_kind"])} · observed {e(citation["observed_on"])} '
                         f'· captured {e(citation["captured_on"])}</p><blockquote><pre>{e(citation["quote"])}</pre>'
                         '</blockquote></details>')
        for limitation in row['limitations']:
            parts.append(f'<p>{e(limitation)}</p>')
        parts.append(f'<p>Next action: {e(row["next_action"])}</p></article></details>')
    parts.append(f'<details><summary>{len(report["targeted_requests"])} remaining evidence requests — drafts, not sent</summary>')
    for request in report['targeted_requests']:
        parts.append(f'<p>{e(request["question"])}</p>')
    parts.append('</details>')
    parts.extend(['<h2>Record a draft review</h2>',
        '<p>Request Evidence requires your explicit judgment that the current sources are insufficient. '
        'Accept remains a discussion annotation; no action confirms technical facts or approves a control.</p>',
        f'<form method="post" action="/review">{hidden()}',
        select('requirement_id', 'Review requirement', [(r['requirement_id'], r['requirement_id'])
                                                      for r in report['requirements']], default_target),
        select('action', 'Draft action', ACTIONS, 'Request Evidence'),
        '<label>Rationale <textarea name="rationale" maxlength="1200" required></textarea></label>',
        '<label><input type="checkbox" name="confirms_insufficiency" value="yes"> '
        'I reviewed the current candidates and confirm they are insufficient for this requirement.</label>',
        '<button type="submit">Record and save review</button></form>',
        '<h2>Review history</h2>'])
    for action in report['analyst_actions']:
        parts.append(f'<p>{e(action["requirement_id"])} · {e(action["action"])} · {e(action["status"])} '
                     f'· {e(action["recorded_at"])}: <span>{e(action["rationale"])}</span></p>')
    for review in report['evidence_gap_reviews']:
        parts.append(f'<p>Evidence-gap review · {e(review["requirement_id"])} · {e(review["status"])} '
                     f'· {e(review["reviewed_on"])}: <span>{e(review["rationale"])}</span></p>')
    linked = {review['need_id'] for review in report['evidence_gap_reviews']}
    for review in report.get('persistence', {}).get('insufficiency_history', []):
        if review['need_id'] not in linked:
            parts.append(f'<p>Historical unlinked review · {e(review["need_id"])} · not current '
                         f'· {e(review["reviewed_on"])}: {e(review["rationale"])}</p>')
    parts.extend(['<h2>Finish and export</h2>',
        '<p>Finishing records this synthetic review. Open gaps and findings remain unresolved; '
        'the vendor decision stays pending and numerical residual risk is unassessed.</p>',
        f'<form method="post" action="/finish">{hidden()}'
        '<button type="submit">Finish review</button></form>',
        '<p><a href="/download.zip">Download assessment package</a> '
        '(report, captured methodology, source manifest and exact original bytes)</p>'])
    return "\n".join(parts)
