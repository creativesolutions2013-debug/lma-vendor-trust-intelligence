"""Durable synthetic analyst journey under real session/SQL/custody boundaries.

Only disposable SQLite files or UUID-owned Actions PostgreSQL schemas are used.
The browser UI, production login, external AI and vendor delivery stay unwired.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
import json
import os
from threading import Event
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, delete, event, func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

import src.authz as authz
import src.resumable_assessment as resumable
import src.tenant_read_scope as scoped
from src.assessment_evidence_access import EvidenceReadRequest
from src.db import (
    Assessment, Base, EngagementAccessGrant, Evidence, OrganizationMembership,
    SyntheticAssessmentRevision, SyntheticEvidenceObject, Vendor,
)
from src.organization_methodology import OrganizationMethodology, default_definition
from src.resumable_assessment_state import encode_draft, parse_state, with_review_state
from src.guided_assessment_demo import complete_review, record_action
from src.server_sessions import InMemorySessionStore, SessionManager, VerifiedSubject
from src.session_identity_source import SessionIdentitySource
from src.synthetic_evidence_custody import SyntheticEvidenceCustodyService
from src.synthetic_custody_guards import synthetic_custody_guard_statements
from src.upload_assessment import Intake, build_assessment, read_upload, record_upload_review
from test_session_identity_source import ISSUER, signing_key, synthetic_code_flow_session
from test_tenant_read_scope import NOW, rows


def _engine(url, schema=None):
    root = create_engine(url, **({"connect_args": {"check_same_thread": False}}
                                if url.startswith("sqlite") else {}))
    if url.startswith("sqlite"):
        @event.listens_for(root, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return root, root.execution_options(schema_translate_map={None: schema}) if schema else root


def _login(ctx, *, signing_key=None):
    ctx.sessions = SessionManager(InMemorySessionStore(), clock=lambda: ctx.clock[0],
                                  idle_seconds=30, absolute_seconds=90)
    ctx.handle = (synthetic_code_flow_session(ctx.sessions, ctx.clock, signing_key)
                  if signing_key is not None else ctx.sessions.issue(
                      VerifiedSubject(ISSUER, "reader", "synthetic-client")))
    ctx.source = SessionIdentitySource(ctx.sessions, ctx.handle, ctx.factory,
                                      clock=lambda: ctx.clock[0])
    ctx.custody = SyntheticEvidenceCustodyService(ctx.factory, identity_source=ctx.source)
    ctx.service = resumable.SyntheticResumableAssessmentService(ctx.factory, identity_source=ctx.source)


@pytest.fixture
def assessment_ctx(tmp_path, monkeypatch):
    configured = os.getenv("DATABASE_URL", "")
    postgres = os.getenv("GITHUB_ACTIONS") == "true" and configured.startswith("postgresql")
    schema = "m7_resume_" + uuid4().hex if postgres else None
    url = configured if postgres else f"sqlite:///{tmp_path / 'synthetic-resume.sqlite'}"
    root, engine = _engine(url, schema)
    if schema:
        with root.begin() as connection:
            connection.execute(CreateSchema(schema))
    ctx = SimpleNamespace(root=root, engine=engine, schema=schema, url=url, clock=[NOW])
    try:
        Base.metadata.create_all(engine)
        ctx.factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        rows(ctx.factory)
        with ctx.factory.begin() as database:
            database.execute(delete(Evidence).where(Evidence.id == 9501))
            database.execute(update(OrganizationMembership).where(OrganizationMembership.id == 501)
                             .values(issuer=ISSUER, subject="reader", expires_at=NOW + timedelta(days=800)))
            database.execute(update(EngagementAccessGrant).where(EngagementAccessGrant.id == 701)
                             .values(expires_at=NOW + timedelta(days=800)))
        monkeypatch.setattr(scoped, "_utc_now", lambda: ctx.clock[0])
        _login(ctx)
        ctx.intake = Intake("1001", "Vendor A", "A allowed service", "Synthetic analytics review",
            as_of=NOW.date(), organization_id="synthetic-a",
            methodology=OrganizationMethodology.from_dict(default_definition("synthetic-a")))
        yield ctx
    finally:
        if schema:
            with ctx.root.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        ctx.root.dispose()


def _source(ctx, name="recovery-plan.txt", content=None, *, requirements=("BCP-01",),
            kind="policy", intake=None, observed_on=None):
    intake = intake or ctx.intake
    if content is None:
        content = (f"Recovery plan\nService: {intake.service}\nEnvironment: {intake.environment}\n"
                   f"Observation date: {ctx.clock[0].date()}\n"
                   "Target RTO 120 minutes and RPO 30 minutes.\n"
                   "A recovery exercise is scheduled; no completed test result is supplied.\n").encode()
    receipt = ctx.custody.save(1001, content, document_name=name)
    assert receipt is not None, "synthetic source staging failed before assessment save"
    # Capture date is the actual immutable ingestion date, independent of the
    # assessment's later re-evaluation date and the original observation date.
    captured = replace(intake, as_of=receipt.created_at.date())
    upload = read_upload(captured, name, content, requirements, kind=kind,
                         observed_on=observed_on or receipt.created_at.date())
    return upload, receipt


def _draft(ctx, sources=None, intake=None):
    if sources is None:
        sources = (_source(ctx),)
    uploads, receipts = zip(*sources)
    return encode_draft(intake or ctx.intake, uploads, receipts)


def _saved(ctx, draft=None, expected=0):
    saved = ctx.service.save(1001, expected_revision=expected, draft=draft or _draft(ctx))
    assert type(saved) is resumable.SavedAssessmentRevision
    assert saved.assessment_id == 1001 and type(saved.revision) is int
    assert len(saved.state_sha256) == 64
    return saved


def _rows(ctx):
    with ctx.factory() as database:
        return tuple(tuple(database.execute(select(model.__table__).order_by(
            *model.__table__.primary_key.columns)).all()) for model in (
                SyntheticAssessmentRevision, SyntheticEvidenceObject, Evidence, Assessment,
                OrganizationMembership, EngagementAccessGrant))


def _count(ctx):
    with ctx.factory() as database:
        return database.execute(select(func.count()).select_from(SyntheticAssessmentRevision)).scalar_one()


def _change(ctx, model, identifier, **changes):
    with ctx.factory.begin() as database:
        database.execute(update(model).where(model.id == identifier).values(**changes))


def _review(ctx, revision, action="Request Evidence", rationale="Provide the completed recovery test and actual RTO/RPO."):
    saved = ctx.service.record_review(1001, expected_revision=revision, requirement_id="BCP-01",
        action=action, rationale=rationale, confirms_insufficiency=action == "Request Evidence")
    assert type(saved) is resumable.SavedAssessmentRevision
    return saved


def _request(receipt):
    return EvidenceReadRequest(receipt.organization_id, receipt.engagement_id, receipt.vendor_id,
                               receipt.assessment_id, receipt.evidence_id)


def test_original_save_leave_restart_resume_review_and_report(assessment_ctx, signing_key):
    ctx = assessment_ctx
    _login(ctx, signing_key=signing_key)
    source, receipt = _source(ctx)
    original = source.evidence.source.content
    saved = _saved(ctx, _draft(ctx, ((source, receipt),)))
    assert saved.revision == 1
    initial = ctx.service.resume(1001)
    assert type(initial) is resumable.ResumedAssessment
    assert initial.revision == saved.revision and initial.state_sha256 == saved.state_sha256
    assert not initial.actions and initial.completion is None
    assert not initial.completion_stale
    assert any(m.status == "Analyst validation required" for row in initial.model.worklist.rows
               if row.requirement_id == "BCP-01" for m in row.need_matches)

    # Dispose all process-owned database/session/assessment objects. A fresh
    # engine and newly signed local code-flow session recover the SQL revision.
    assert ctx.sessions.revoke(ctx.handle)
    old_engine = ctx.root
    old_engine.dispose()
    ctx.root, ctx.engine = _engine(ctx.url, ctx.schema)
    ctx.factory = sessionmaker(bind=ctx.engine, expire_on_commit=False, autoflush=False)
    _login(ctx, signing_key=signing_key)
    del initial, saved, source, receipt
    restored = ctx.service.resume(1001)
    assert restored is not None and restored.revision == 1
    assert restored.uploads[0].evidence.source.content == original
    assert restored.intake.methodology.fingerprint == ctx.intake.methodology.fingerprint

    requested = _review(ctx, restored.revision)
    reviewed = ctx.service.resume(1001)
    requests = [r for r in reviewed.report["targeted_requests"] if "BCP-01" in r["requirement_ids"]]
    assert requests and requests[0]["question"] == "Provide the completed recovery test and actual RTO/RPO."
    assert reviewed.report["evidence_gap_reviews"][0]["status"] == "Current"
    found = _review(ctx, requested.revision, "Create Finding", "<script>Validate missing recovery operating proof</script>")
    finished = ctx.service.finish(1001, expected_revision=found.revision)
    assert finished is not None and finished.revision == found.revision + 1
    result = ctx.service.resume(1001)
    assert result.completion is not None and result.completion_stale is False
    assert result.report["session_only"] is False
    assert result.report["risk"]["residual_score"] is None
    assert result.report["review_completion"]["vendor_approved"] is False
    assert all(row["outcome"] not in ("Met", "Risk Identified") for row in result.report["requirements"])
    finding = result.report["findings"][0]
    assert finding["context_status"] == "Current" and finding["citations"]
    assert finding["resolved"] is False
    assert all(c["quote"] in original.decode() for c in finding["citations"])
    with ZipFile(BytesIO(result.package)) as package:
        report = json.loads(package.read("report.json"))
        assert report == result.report
        artifact = json.loads(package.read("manifest.json"))["artifacts"][0]
        assert package.read(artifact["archive_path"]) == original
        assert artifact["sha256"] == sha256(original).hexdigest()
        assert json.loads(package.read("methodology.json"))["organization_id"] == "synthetic-a"
        html = package.read("summary.html").decode()
        assert "&lt;script&gt;" in html and "<script>" not in html
    assert _count(ctx) == 4


def test_four_maximum_size_originals_round_trip_without_silent_truncation(assessment_ctx):
    ctx = assessment_ctx
    sources = tuple(_source(ctx, f"context-{index}.txt", bytes([65 + index]) * 65536,
                            requirements=()) for index in range(4))
    saved = _saved(ctx, _draft(ctx, sources))
    result = ctx.service.resume(1001)
    assert result is not None and result.revision == saved.revision
    assert [u.evidence.source.content for u in result.uploads] == [u.evidence.source.content for u, _ in sources]
    with ZipFile(BytesIO(result.package)) as archive:
        artifacts = json.loads(archive.read("manifest.json"))["artifacts"]
        assert len(artifacts) == 4
        originals = {u.evidence.source.filename: u.evidence.source.content for u, _ in sources}
        for artifact in artifacts:
            assert archive.read(artifact["archive_path"]) == originals[artifact["filename"]]
            assert artifact["byte_count"] == 65536
    before = _rows(ctx)
    assert ctx.custody.save(1001, b"X" * 65537, document_name="over-custody-limit.txt") is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("change", ["new_source", "intake", "policy", "threshold", "routing", "metadata"])
def test_config_revision_preserves_stale_reviews_and_requires_explicit_rereview(assessment_ctx, change):
    ctx = assessment_ctx
    original = _source(ctx)
    saved = _saved(ctx, _draft(ctx, (original,)))
    requested = _review(ctx, saved.revision)
    finished = ctx.service.finish(1001, expected_revision=requested.revision)
    old = ctx.service.resume(1001)
    assert old.completion is not None and not old.completion_stale
    old_review = old.report["evidence_gap_reviews"][0]
    intake, sources = ctx.intake, (original,)
    if change == "new_source":
        response = _source(ctx, "recovery-test.txt", b"Completed synthetic recovery exercise. Achieved RTO 300 minutes.", kind="test")
        sources += (response,)
    elif change == "intake":
        intake = replace(intake, use_case="New synthetic reporting use case")
    elif change in ("policy", "threshold"):
        definition = intake.methodology.definition
        definition["version"] = "2"
        if change == "threshold":
            definition["assurance"]["rto_minutes"] = 60
        intake = replace(intake, methodology=OrganizationMethodology.from_dict(definition))
    elif change == "routing":
        upload, receipt = original
        sources = ((replace(upload, requirements=("ENC-01",)), receipt),)
    else:
        upload, receipt = original
        revised = read_upload(intake, receipt.document_name, upload.evidence.source.content,
                              upload.requirements, kind="assertion", observed_on=intake.as_of)
        sources = ((revised, receipt),)
    revised = _saved(ctx, _draft(ctx, sources, intake), expected=finished.revision)
    result = ctx.service.resume(1001)
    assert result.revision == revised.revision
    assert result.completion is None and result.completion_stale is True
    assert len(result.actions) == 1 and result.actions == old.actions
    assert result.report["analyst_actions"][0]["status"] == "Stale context"
    history = result.report["evidence_gap_reviews"]
    assert history and history[0]["status"] == "Stale context"
    assert history[0]["context_fingerprint"] == old_review["context_fingerprint"]
    assert history[0]["source_fingerprints"] == old_review["source_fingerprints"]
    assert result.report["review_completion"]["vendor_approved"] is False
    # Re-review is a separate explicit authorized command. It never rewrites the
    # original annotation's fingerprint or turns a draft into control approval.
    rerun = _review(ctx, revised.revision)
    current = ctx.service.resume(1001)
    assert rerun is not None and len(current.actions) == 2
    assert current.report["analyst_actions"][-1]["status"] == "Current"
    assert current.report["risk"]["residual_score"] is None


def test_resume_rechecks_server_date_without_redating_originals(assessment_ctx):
    ctx = assessment_ctx
    source = _source(ctx)
    saved = _saved(ctx, _draft(ctx, (source,)))
    requested = _review(ctx, saved.revision)
    assert ctx.service.finish(1001, expected_revision=requested.revision) is not None
    original = ctx.service.resume(1001)
    ctx.clock[0] += timedelta(days=366)
    _login(ctx)
    restored = ctx.service.resume(1001)
    assert restored is not None and restored.intake.as_of == ctx.clock[0].date()
    assert restored.uploads[0].evidence.source.captured_on == source[1].created_at.date()
    assert restored.uploads[0].evidence.source.observed_on == source[0].evidence.source.observed_on
    assert restored.uploads[0].evidence.source.content == source[0].evidence.source.content
    assert restored.actions == original.actions
    assert restored.completion is None and restored.completion_stale is True
    assert restored.report["analyst_actions"][0]["status"] == "Stale context"
    assert restored.report["evidence_gap_reviews"][0]["status"] == "Stale context"
    row = next(row for row in restored.report["requirements"] if row["requirement_id"] == "BCP-01")
    assert row["outcome"] == "Evidence Missing"


@pytest.mark.parametrize("identifier", [1002, 2001, 3001, 4001, 5001, 99999, None, True, "1001", 0, -1, 2**64])
def test_wrong_assessment_never_saves_resumes_or_mutates(assessment_ctx, identifier):
    ctx = assessment_ctx
    draft = _draft(ctx)
    before = _rows(ctx)
    assert ctx.service.save(identifier, expected_revision=0, draft=draft) is None
    assert ctx.service.resume(identifier) is None
    assert ctx.service.record_review(identifier, expected_revision=0, requirement_id="BCP-01",
        action="Create Finding", rationale="Synthetic finding") is None
    assert ctx.service.finish(identifier, expected_revision=0) is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("revision", [None, True, -1, "0", 2**64, 1, 2])
def test_initial_save_requires_exact_zero_expected_revision(assessment_ctx, revision):
    ctx = assessment_ctx
    draft = _draft(ctx)
    before = _rows(ctx)
    assert ctx.service.save(1001, expected_revision=revision, draft=draft) is None
    assert _rows(ctx) == before


def test_replayed_save_review_finish_and_duplicate_finding_do_not_append(assessment_ctx):
    ctx = assessment_ctx
    draft = _draft(ctx)
    saved = _saved(ctx, draft)
    before = _rows(ctx)
    assert ctx.service.save(1001, expected_revision=0, draft=draft) is None
    assert ctx.service.record_review(1001, expected_revision=0, requirement_id="BCP-01",
        action="Create Finding", rationale="Synthetic concern") is None
    assert ctx.service.finish(1001, expected_revision=0) is None
    assert _rows(ctx) == before
    finding = _review(ctx, saved.revision, "Create Finding", "Synthetic concern")
    before = _rows(ctx)
    assert ctx.service.record_review(1001, expected_revision=finding.revision, requirement_id="BCP-01",
        action="Create Finding", rationale="Synthetic concern") is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("case", ["no_confirm", "unknown_requirement", "unknown_action", "empty_reason"])
def test_review_requires_explicit_valid_current_command(assessment_ctx, case):
    ctx = assessment_ctx
    saved = _saved(ctx)
    command = dict(expected_revision=saved.revision, requirement_id="BCP-01",
                   action="Request Evidence", rationale="Provide actual operating proof.",
                   confirms_insufficiency=True)
    command.update({"no_confirm": {"confirms_insufficiency": False},
                    "unknown_requirement": {"requirement_id": "UNKNOWN"},
                    "unknown_action": {"action": "Approve vendor"},
                    "empty_reason": {"rationale": " "}}[case])
    before = _rows(ctx)
    assert ctx.service.record_review(1001, **command) is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("failure", ["member_revoke", "member_expire", "grant_revoke", "grant_expire",
    "session_revoke", "session_rotate", "idle", "absolute", "membership_ambiguity", "read_permission", "manage_permission"])
def test_saved_state_and_all_mutations_need_current_authority(assessment_ctx, monkeypatch, failure):
    ctx = assessment_ctx
    draft = _draft(ctx)
    saved = _saved(ctx, draft)
    if failure.startswith("member_"):
        _change(ctx, OrganizationMembership, 501, **({"status": "revoked"} if failure.endswith("revoke")
                                                   else {"expires_at": NOW}))
    elif failure.startswith("grant_"):
        _change(ctx, EngagementAccessGrant, 701, **({"status": "revoked"} if failure.endswith("revoke")
                                                  else {"expires_at": NOW}))
    elif failure == "membership_ambiguity":
        with ctx.factory.begin() as database:
            database.execute(insert(OrganizationMembership).values(id=990, organization_id=2, issuer=ISSUER,
                subject="reader", role=authz.ROLE_ANALYST, status="active", valid_from=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(days=1)))
    elif failure in ("read_permission", "manage_permission"):
        permission = authz.PERMISSION_EVIDENCE_READ if failure == "read_permission" else authz.PERMISSION_ASSESSMENT_MANAGE
        monkeypatch.setitem(authz.ROLE_PERMISSIONS, authz.ROLE_ANALYST,
                            authz.ROLE_PERMISSIONS[authz.ROLE_ANALYST] - {permission})
    elif failure.startswith("session_"):
        assert getattr(ctx.sessions, failure.split("_", 1)[1])(ctx.handle)
    else:
        ctx.clock[0] += timedelta(seconds=30 if failure == "idle" else 90)
    before = _rows(ctx)
    assert ctx.service.resume(1001) is None
    assert ctx.service.save(1001, expected_revision=saved.revision, draft=draft) is None
    assert ctx.service.record_review(1001, expected_revision=saved.revision, requirement_id="BCP-01",
        action="Create Finding", rationale="Synthetic concern") is None
    assert ctx.service.finish(1001, expected_revision=saved.revision) is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("raw", [None, "{}", bytearray(b"{}"), b"", b"{}", b"null", b"[]", b"\xff",
    b"x" * 65537, b'{"schema":1,"schema":1}', b'cos\nsystem\n(S"synthetic"\ntR.'])
def test_malformed_oversized_and_pickle_state_deny_without_partial_revision(assessment_ctx, raw):
    ctx = assessment_ctx
    before = _rows(ctx)
    assert ctx.service.save(1001, expected_revision=0, draft=raw) is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("field,value", [("vendor_approved", True), ("risk_score", 0),
    ("technical_facts_confirmed", True), ("principal", {"role": "Admin"}), ("session_handle", "caller-selected")])
def test_unknown_authority_or_decision_fields_never_enter_saved_state(assessment_ctx, field, value):
    ctx = assessment_ctx
    payload = json.loads(_draft(ctx))
    payload[field] = value
    before = _rows(ctx)
    assert ctx.service.save(1001, expected_revision=0, draft=json.dumps(payload).encode()) is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("field,value", [("organization_id", 2), ("vendor_id", 22),
    ("engagement_id", 102), ("assessment_id", 1002), ("evidence_id", 9001),
    ("evidence_id", 999999), ("generation", "f" * 32), ("sha256", "f" * 64),
    ("byte_length", 65536), ("filename", "another-original.txt"),
    ("captured_on", "2020-01-01"), ("source_fingerprint", "f" * 64)])
def test_exact_custody_reference_and_original_binding_are_required(assessment_ctx, field, value):
    ctx = assessment_ctx
    packet = json.loads(_draft(ctx))
    packet["sources"][0][field] = value
    before = _rows(ctx)
    assert ctx.service.save(1001, expected_revision=0, draft=json.dumps(packet).encode()) is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("field,value", [("assessment_id", "1002"), ("organization_id", "synthetic-b"),
    ("vendor", "Invented vendor"), ("service", "A ungranted sibling")])
def test_caller_intake_cannot_relabel_sql_ownership(assessment_ctx, field, value):
    ctx = assessment_ctx
    packet = json.loads(_draft(ctx))
    packet["intake"][field] = value
    before = _rows(ctx)
    assert ctx.service.save(1001, expected_revision=0, draft=json.dumps(packet).encode()) is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("injected", ["action", "need_review", "completion"])
def test_save_rejects_even_well_formed_client_supplied_native_review_state(assessment_ctx, injected):
    ctx = assessment_ctx
    source = _source(ctx)
    packet = parse_state(_draft(ctx, (source,)))
    model = build_assessment(ctx.intake, (source[0],))
    actions, completion = (), None
    if injected == "action":
        actions = record_action(model, (), "BCP-01", "Challenge", "A caller-authored old annotation")
    elif injected == "need_review":
        model, _ = record_upload_review(model, (), "BCP-01", "Request Evidence",
            "A caller-authored insufficiency judgment", confirms_insufficiency=True)
    else:
        completion = complete_review(model, ())
    forged = with_review_state(packet, model, actions, completion)
    before = _rows(ctx)
    assert ctx.service.save(1001, expected_revision=0, draft=json.dumps(forged).encode()) is None
    assert _rows(ctx) == before


def test_legacy_key_alias_cannot_supply_an_original_for_a_saved_assessment(assessment_ctx):
    ctx = assessment_ctx
    source, receipt = _source(ctx)
    _change(ctx, Evidence, 9001, storage_path=f"vendors/11/evidence/m7_{receipt.generation}.bin",
            file_hash=receipt.sha256)
    packet = json.loads(_draft(ctx, ((source, receipt),)))
    packet["sources"][0]["evidence_id"] = 9001
    before = _rows(ctx)
    assert ctx.service.save(1001, expected_revision=0, draft=json.dumps(packet).encode()) is None
    assert _rows(ctx) == before
    assert ctx.custody.retrieve(_request(receipt), generation=receipt.generation).content == source.evidence.source.content


def test_original_owner_reassignment_is_blocked_and_state_remains_readable(assessment_ctx):
    ctx = assessment_ctx
    saved = _saved(ctx)
    before = _rows(ctx)
    with pytest.raises(DBAPIError):
        _change(ctx, Vendor, 11, organization_id=2)
    with pytest.raises(DBAPIError):
        _change(ctx, Assessment, 1001, engagement_id=102)
    assert _rows(ctx) == before
    assert ctx.service.resume(1001).revision == saved.revision


def test_resume_rehashes_original_bytes_after_isolated_admin_tampering(assessment_ctx):
    ctx = assessment_ctx
    source, receipt = _source(ctx)
    draft = _draft(ctx, ((source, receipt),))
    saved = _saved(ctx, draft)
    quote = ctx.engine.dialect.identifier_preparer.quote
    relation = (quote(ctx.schema) + "." if ctx.schema else "") + quote("synthetic_evidence_objects")
    postgres = ctx.engine.dialect.name == "postgresql"
    trigger = quote("m7_custody_no_mutation" if postgres else "m7_custody_no_update")
    tampered = b"X" + source.evidence.source.content[1:]
    with ctx.engine.begin() as connection:
        connection.exec_driver_sql(f"ALTER TABLE {relation} DISABLE TRIGGER {trigger}" if postgres else
                                   f"DROP TRIGGER {trigger}")
        connection.execute(update(SyntheticEvidenceObject).where(
            SyntheticEvidenceObject.evidence_id == receipt.evidence_id).values(payload=tampered))
        if postgres:
            connection.exec_driver_sql(f"ALTER TABLE {relation} ENABLE ALWAYS TRIGGER {trigger}")
        else:
            statement = next(s for s in synthetic_custody_guard_statements(ctx.engine.dialect)
                             if s.startswith("CREATE TRIGGER m7_custody_no_update "))
            connection.exec_driver_sql(statement)
    # Restore guard health first: the denial must come from byte verification.
    before = _rows(ctx)
    assert ctx.service.resume(1001) is None
    assert ctx.service.save(1001, expected_revision=saved.revision, draft=draft) is None
    assert _rows(ctx) == before


@pytest.mark.parametrize("failure", ["revision_insert", "commit"])
def test_revision_write_and_commit_failures_leave_staged_original_but_no_revision(assessment_ctx, failure):
    ctx = assessment_ctx
    draft = _draft(ctx)
    before, invoked = _rows(ctx), []
    def fail_insert(_connection, _cursor, statement, _parameters, _context, _many):
        normalized = statement.lstrip().upper().replace('"', '')
        if normalized.startswith("INSERT INTO ") and SyntheticAssessmentRevision.__tablename__.upper() in normalized:
            invoked.append(True)
            raise RuntimeError("synthetic revision insertion failure")
    def fail_commit(_database):
        invoked.append(True)
        raise RuntimeError("synthetic commit failure")
    target, event_name, hook = ((ctx.engine, "before_cursor_execute", fail_insert) if failure == "revision_insert"
                               else (ctx.factory, "before_commit", fail_commit))
    event.listen(target, event_name, hook)
    try:
        assert ctx.service.save(1001, expected_revision=0, draft=draft) is None
        assert invoked == [True]
    finally:
        event.remove(target, event_name, hook)
    assert _rows(ctx) == before and _count(ctx) == 0
    assert len(before[1]) == 1  # Source staging was a distinct completed operation.


def test_lost_acknowledgement_recovers_latest_revision_and_blocks_blind_retry(assessment_ctx, monkeypatch):
    ctx = assessment_ctx
    draft = _draft(ctx)
    original, invoked = ctx.sessions._store.operation_lease, []
    @contextmanager
    def failed_cleanup(key):
        with original(key):
            yield
        invoked.append(True)
        raise RuntimeError("synthetic acknowledgement failure after SQL commit")
    with monkeypatch.context() as patch:
        patch.setattr(ctx.sessions._store, "operation_lease", failed_cleanup)
        assert ctx.service.save(1001, expected_revision=0, draft=draft) is None
        assert invoked == [True]
    assert _count(ctx) == 1
    latest = ctx.service.resume(1001)
    assert latest is not None and latest.revision == 1
    assert ctx.service.save(1001, expected_revision=0, draft=draft) is None
    assert _count(ctx) == 1


@pytest.mark.parametrize("operation", ["save", "resume"])
@pytest.mark.parametrize("stage", ["commit", "cleanup"])
@pytest.mark.parametrize("deadline", ["membership", "grant", "idle", "absolute"])
def test_deadlines_after_final_sql_check_withhold_revision_receipt_and_resumed_bytes(
        assessment_ctx, monkeypatch, operation, stage, deadline):
    ctx = assessment_ctx
    draft = _draft(ctx)
    saved = _saved(ctx, draft)
    if deadline in ("membership", "grant"):
        _change(ctx, OrganizationMembership if deadline == "membership" else EngagementAccessGrant,
                501 if deadline == "membership" else 701, expires_at=NOW + timedelta(seconds=5))
    advance = timedelta(seconds=31 if deadline == "idle" else 91 if deadline == "absolute" else 10)
    invoked = []
    def expire(_database):
        invoked.append(True)
        ctx.clock[0] += advance
    original = ctx.sessions._store.operation_lease
    @contextmanager
    def slow_cleanup(key):
        with original(key):
            yield
        expire(None)
    if stage == "commit":
        event.listen(ctx.factory, "before_commit", expire)
    else:
        monkeypatch.setattr(ctx.sessions._store, "operation_lease", slow_cleanup)
    try:
        result = (ctx.service.save(1001, expected_revision=saved.revision, draft=draft)
                  if operation == "save" else ctx.service.resume(1001))
        assert result is None and invoked == [True]
    finally:
        if stage == "commit":
            event.remove(ctx.factory, "before_commit", expire)
    # SQL committed before the acknowledgement/deadline failure. Never promise
    # rollback or disclose the already materialized receipt/report/originals.
    assert _count(ctx) == (2 if operation == "save" else 1)


@pytest.mark.parametrize("kind", ["source", "factory", "store"])
def test_dependency_change_during_commit_withholds_state(assessment_ctx, monkeypatch, kind):
    ctx = assessment_ctx
    draft = _draft(ctx)
    called = []
    def replace_dependency(_database):
        called.append(True)
        if kind == "source":
            monkeypatch.setattr(ctx.service, "_identity_source", SessionIdentitySource(
                ctx.sessions, ctx.handle, ctx.factory, clock=ctx.source._clock))
        elif kind == "factory":
            monkeypatch.setattr(ctx.source, "_database_sessions", sessionmaker(bind=ctx.engine))
        else:
            replacement = InMemorySessionStore()
            replacement._records = dict(ctx.sessions._store._records)
            monkeypatch.setattr(ctx.sessions, "_store", replacement)
    event.listen(ctx.factory, "before_commit", replace_dependency)
    try:
        assert ctx.service.save(1001, expected_revision=0, draft=draft) is None
        assert called == [True]
    finally:
        event.remove(ctx.factory, "before_commit", replace_dependency)


def test_dto_demo_role_and_missing_configuration_cannot_supply_server_identity(assessment_ctx):
    ctx = assessment_ctx
    draft = _draft(ctx)
    identity = ctx.source.authenticated_identity()
    for service in (resumable.SyntheticResumableAssessmentService(),
        resumable.SyntheticResumableAssessmentService(ctx.factory),
        resumable.SyntheticResumableAssessmentService(ctx.factory, identity_source=identity),
        resumable.SyntheticResumableAssessmentService(ctx.factory,
            identity_source=SimpleNamespace(authenticated_identity=lambda: identity))):
        assert service.save(1001, expected_revision=0, draft=draft) is None
        assert service.resume(1001) is None
    assert _count(ctx) == 0


def test_postgres_simultaneous_writers_append_once_and_reject_stale_expected_revision(assessment_ctx):
    ctx = assessment_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires isolated Actions PostgreSQL and independent connections")
    draft = _draft(ctx)
    # Independent server stores prevent the synthetic store-wide lease from
    # hiding the PostgreSQL writer race. Only SQL coordinates these two saves.
    manager = SessionManager(InMemorySessionStore(), clock=lambda: ctx.clock[0],
                             idle_seconds=30, absolute_seconds=90)
    handle = manager.issue(VerifiedSubject(ISSUER, "reader", "synthetic-client"))
    competitor_factory = sessionmaker(bind=ctx.engine, expire_on_commit=False, autoflush=False)
    source = SessionIdentitySource(manager, handle, competitor_factory, clock=lambda: ctx.clock[0])
    competitor = resumable.SyntheticResumableAssessmentService(competitor_factory, identity_source=source)
    committing, release, second_sql = Event(), Event(), Event()
    seen = []
    def observe_competing_sql(orm_execute):
        if getattr(orm_execute.statement, "_for_update_arg", None) is not None:
            second_sql.set()
    def pause(_database):
        seen.append(True)
        committing.set()
        assert release.wait(5), "first revision save was not released"
    event.listen(ctx.factory, "before_commit", pause)
    event.listen(competitor_factory, "do_orm_execute", observe_competing_sql)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(ctx.service.save, 1001, expected_revision=0, draft=draft)
            try:
                assert committing.wait(5)
                def competing():
                    return competitor.save(1001, expected_revision=0, draft=draft)
                second = workers.submit(competing)
                assert second_sql.wait(5), "competing writer did not reach SQL row locking"
                assert not second.done(), "competing writer bypassed the locked assessment"
            finally:
                release.set()
            one, two = first.result(timeout=10), second.result(timeout=10)
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause)
        event.remove(competitor_factory, "do_orm_execute", observe_competing_sql)
    assert one is not None and two is None and seen == [True]
    assert _count(ctx) == 1 and ctx.service.resume(1001).revision == 1


@pytest.mark.parametrize("mutation", ["grant_revoke", "membership_insert", "assessment_delete"])
def test_postgres_authority_mutations_wait_through_revision_commit(assessment_ctx, mutation):
    ctx = assessment_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires isolated Actions PostgreSQL and independent connections")
    draft = _draft(ctx)
    committing, release = Event(), Event()
    def pause(_database):
        committing.set()
        assert release.wait(5), "revision save was not released"
    event.listen(ctx.factory, "before_commit", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as workers:
            saving = workers.submit(ctx.service.save, 1001, expected_revision=0, draft=draft)
            try:
                assert committing.wait(5)
                with ctx.engine.connect() as connection:
                    with pytest.raises(DBAPIError) as error, connection.begin():
                        connection.exec_driver_sql("SET LOCAL lock_timeout='150ms'")
                        if mutation == "grant_revoke":
                            connection.execute(update(EngagementAccessGrant).where(
                                EngagementAccessGrant.id == 701).values(status="revoked"))
                        elif mutation == "membership_insert":
                            connection.execute(insert(OrganizationMembership).values(id=990,
                                organization_id=2, issuer=ISSUER, subject="reader", role=authz.ROLE_ANALYST,
                                status="active", valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1)))
                        else:
                            connection.execute(delete(Assessment).where(Assessment.id == 1001))
                    assert (getattr(error.value.orig, "sqlstate", None)
                            or getattr(error.value.orig, "pgcode", None)) == "55P03"
            finally:
                release.set()
            assert saving.result(timeout=10) is not None
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause)
    assert ctx.service.resume(1001) is not None
