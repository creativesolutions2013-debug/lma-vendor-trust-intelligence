"""Disposable local pilot fixtures; no external database or real credentials."""
from hashlib import sha256
import builtins
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from src.synthetic_pilot_runtime import prepare_runtime


PORT = 18443
ISSUER = f"https://127.0.0.1:{PORT}/synthetic-idp"
SUBJECT = "synthetic-analyst"


@pytest.fixture(autouse=True)
def development_only(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.mark.parametrize("mode", [None, "production", "", "Development", "demo"])
def test_denied_mode_stops_before_database_import_or_filesystem_creation(tmp_path, monkeypatch, mode):
    monkeypatch.delenv("AUTH_MODE", raising=False) if mode is None else monkeypatch.setenv("AUTH_MODE", mode)
    calls = []
    original = builtins.__import__
    def observe(name, *args, **kwargs):
        if name == "src.db":
            calls.append(name)
            pytest.fail("denied runtime imported the database")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", observe)
    directory = tmp_path / "runtime"
    with pytest.raises(ValueError, match="AUTH_MODE=development"):
        prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    assert not directory.exists() and calls == []


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "sqlite:////tmp/unknown.db", "postgresql://synthetic.invalid/private"])
def test_external_database_configuration_is_refused_before_import(tmp_path, monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValueError, match="unset DATABASE_URL"):
        prepare_runtime(tmp_path / "runtime", PORT, ISSUER, SUBJECT)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mode,database,message", [
    (None, None, "requires explicit AUTH_MODE=development"),
    ("production", None, "requires explicit AUTH_MODE=development"),
    ("development", "postgresql://synthetic.invalid/private", "Unset DATABASE_URL"),
])
def test_actual_entrypoint_denies_before_database_import_password_or_files(tmp_path, mode, database, message):
    hooks, working = tmp_path / "hooks", tmp_path / "working"
    hooks.mkdir()
    working.mkdir(mode=0o500)
    (hooks / "sitecustomize.py").write_text(
        "import builtins\n"
        "_original = builtins.__import__\n"
        "def guarded(name, *args, **kwargs):\n"
        "    if name in ('src.db', 'getpass'):\n"
        "        raise AssertionError('FORBIDDEN_STARTUP_IMPORT: ' + name)\n"
        "    return _original(name, *args, **kwargs)\n"
        "builtins.__import__ = guarded\n"
    )
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(hooks), str(Path(__file__).resolve().parents[1]))),
                       PYTHONDONTWRITEBYTECODE="1")
    if mode is None:
        environment.pop("AUTH_MODE", None)
    else:
        environment["AUTH_MODE"] = mode
    environment.pop("DATABASE_URL", None)
    if database:
        environment["DATABASE_URL"] = database
    try:
        result = subprocess.run([sys.executable, "-B", "-m", "src.synthetic_analyst_pilot",
            "--directory", str(working / "runtime"), "--port", str(PORT)], cwd=working,
            env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
        assert message in result.stderr
        assert "FORBIDDEN_STARTUP_IMPORT" not in result.stderr
        assert "Choose a synthetic-only" not in result.stdout + result.stderr
        assert result.stdout == "" and list(working.iterdir()) == []
    finally:
        working.chmod(0o700)


@pytest.mark.parametrize("port,issuer,subject", [(True, ISSUER, SUBJECT), (0, ISSUER, SUBJECT),
    (443, "https://127.0.0.1:443/synthetic-idp", SUBJECT),
    (65536, ISSUER, SUBJECT), (PORT, "https://external.synthetic.invalid", SUBJECT),
    (PORT, ISSUER, "arbitrary-account")])
def test_runtime_cannot_seed_an_arbitrary_identity_or_origin(tmp_path, port, issuer, subject):
    with pytest.raises(ValueError, match="fixed localhost"):
        prepare_runtime(tmp_path / "runtime", port, issuer, subject)
    assert list(tmp_path.iterdir()) == []


def test_new_runtime_has_private_files_fixed_scope_and_localhost_tls(tmp_path):
    from cryptography import x509
    from sqlalchemy import select
    from src.db import Assessment, EngagementAccessGrant, OrganizationMembership

    directory = tmp_path / "runtime"
    runtime = prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    try:
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert {path.name for path in directory.iterdir()} == {"runtime.json", "pilot.sqlite", "localhost.crt", "localhost.key"}
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir())
        assert runtime.certfile == str(directory / "localhost.crt")
        assert runtime.keyfile == str(directory / "localhost.key")
        certificate = x509.load_pem_x509_certificate(Path(runtime.certfile).read_bytes())
        sans = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        assert [str(value.value) for value in sans] == ["127.0.0.1"]
        with runtime.factory() as session:
            assert session.execute(select(Assessment.id)).scalars().all() == [1001]
            member = session.get(OrganizationMembership, 501)
            assert (member.issuer, member.subject, member.role, member.status) == (ISSUER, SUBJECT, "Analyst", "active")
            assert session.get(EngagementAccessGrant, 701).engagement_id == 101
        assert runtime.intake.assessment_id == "1001"
        assert runtime.intake.organization_id == "synthetic-pilot"
        assert runtime.intake.methodology.definition["organization_id"] == "synthetic-pilot"
        assert runtime.intake.vendor == "Synthetic Vendor" and runtime.intake.service == "Synthetic Analytics"
        assert not any("password" in name or "signing" in name for name in (path.name for path in directory.iterdir()))
    finally:
        runtime.close()


def test_restart_preserves_history_and_revoked_authorization_without_schema_writes(tmp_path, monkeypatch):
    from sqlalchemy import select, update
    from src.db import Base, Evidence, OrganizationMembership, EngagementAccessGrant, SyntheticAssessmentRevision, SyntheticEvidenceObject
    from test_synthetic_custody_migration import object_values
    from test_synthetic_revision_migration import revision_values

    directory = tmp_path / "runtime"
    first = prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    with first.factory.begin() as session:
        original = object_values(issuer=ISSUER, subject=SUBJECT)
        session.execute(Evidence.__table__.insert(), dict(id=9001, vendor_id=11, assessment_id=1001,
            document_type="Synthetic", document_name=original["document_name"],
            storage_path=original["storage_key"], file_hash=original["sha256"]))
        session.execute(SyntheticEvidenceObject.__table__.insert(), original)
        session.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values(issuer=ISSUER, subject=SUBJECT))
        session.execute(update(OrganizationMembership).where(OrganizationMembership.id == 501).values(status="revoked", role="Viewer"))
        session.execute(update(EngagementAccessGrant).where(EngagementAccessGrant.id == 701).values(status="revoked"))
    first.close()
    before = {path.name: sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}
    def no_schema(*args, **kwargs):
        pytest.fail("restart attempted schema initialization")
    monkeypatch.setattr(Base.metadata, "create_all", no_schema)
    second = prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    try:
        with second.factory() as session:
            member = session.get(OrganizationMembership, 501)
            assert (member.status, member.role) == ("revoked", "Viewer")
            assert session.get(EngagementAccessGrant, 701).status == "revoked"
            assert session.execute(select(SyntheticAssessmentRevision.revision)).scalars().all() == [1]
            assert session.get(SyntheticEvidenceObject, 9001).payload == original["payload"]
        assert {path.name: sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()} == before
        assert second.intake == first.intake
    finally:
        second.close()


@pytest.mark.parametrize("kind", ["empty", "database", "public", "extra"])
def test_unknown_existing_directories_and_database_files_are_not_adopted(tmp_path, kind):
    directory = tmp_path / "runtime"
    directory.mkdir(mode=0o700 if kind != "public" else 0o755)
    if kind == "database":
        (directory / "pilot.sqlite").write_bytes(b"unrelated synthetic placeholder")
    elif kind == "extra":
        (directory / "unknown.txt").write_text("synthetic")
    before = tuple(directory.iterdir())
    with pytest.raises(ValueError, match="unknown or nonprivate"):
        prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    assert tuple(directory.iterdir()) == before


@pytest.mark.parametrize("target", ["directory", "ancestor", "pilot.sqlite", "runtime.json", "localhost.key", "localhost.crt"])
def test_runtime_refuses_symlinked_directory_ancestors_or_files(tmp_path, target):
    directory = tmp_path / "runtime"
    if target in ("directory", "ancestor"):
        real = tmp_path / "real"
        real.mkdir(mode=0o700)
        link = tmp_path / "linked"
        link.symlink_to(real, target_is_directory=True)
        directory = link if target == "directory" else link / "runtime"
    else:
        runtime = prepare_runtime(directory, PORT, ISSUER, SUBJECT)
        runtime.close()
        owned = directory / target
        moved = tmp_path / (target + ".moved")
        owned.rename(moved)
        owned.symlink_to(moved)
    with pytest.raises(ValueError, match="symlink|private regular"):
        prepare_runtime(directory, PORT, ISSUER, SUBJECT)


@pytest.mark.parametrize("target", ["pilot.sqlite", "runtime.json", "localhost.key", "localhost.crt"])
def test_runtime_refuses_hardlinked_or_public_files(tmp_path, target):
    directory = tmp_path / "runtime"
    runtime = prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    runtime.close()
    path = directory / target
    os.link(path, tmp_path / "second-link")
    with pytest.raises(ValueError, match="private regular"):
        prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    (tmp_path / "second-link").unlink()
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private regular"):
        prepare_runtime(directory, PORT, ISSUER, SUBJECT)


def test_restart_rejects_different_origin_or_marker_and_never_reseeds(tmp_path):
    directory = tmp_path / "runtime"
    runtime = prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    runtime.close()
    with pytest.raises(ValueError, match="origin or format"):
        prepare_runtime(directory, PORT + 1, f"https://127.0.0.1:{PORT + 1}/synthetic-idp", SUBJECT)
    marker = directory / "runtime.json"
    packet = json.loads(marker.read_text())
    packet["format"] = "unknown"
    marker.write_text(json.dumps(packet, sort_keys=True, separators=(",", ":")))
    with pytest.raises(ValueError, match="origin or format"):
        prepare_runtime(directory, PORT, ISSUER, SUBJECT)


def test_known_marker_cannot_adopt_an_empty_or_missing_guard_database(tmp_path):
    directory = tmp_path / "runtime"
    runtime = prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    with runtime.engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER m7_revision_insert")
    runtime.close()
    with pytest.raises(PermissionError, match="guards are unavailable"):
        prepare_runtime(directory, PORT, ISSUER, SUBJECT)
    (directory / "pilot.sqlite").write_bytes(b"")
    with pytest.raises(ValueError, match="schema is incomplete"):
        prepare_runtime(directory, PORT, ISSUER, SUBJECT)
