"""Private local fixtures for the explicitly development-only synthetic pilot.

No production database, identity signing key or password is configured or stored
here. A known runtime can be reopened without seeding or changing authorization.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import stat


_FILES = {"runtime.json", "pilot.sqlite", "localhost.crt", "localhost.key"}


@dataclass
class SyntheticPilotRuntime:
    factory: object
    intake: object
    certfile: str
    keyfile: str
    engine: object
    vendor_submissions: bool = False

    def close(self):
        self.engine.dispose()


def _regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid()):
        raise ValueError("Synthetic pilot runtime files must be private regular files.")


def _private_write(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(content)


def _directory(path):
    # Check existing ancestors without resolving links to a different location.
    for ancestor in (*reversed(path.parents), path):
        if ancestor.is_symlink():
            raise ValueError("Synthetic pilot runtime paths cannot contain symlinks.")
    if path.exists():
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
                or info.st_uid != os.getuid() or {entry.name for entry in path.iterdir()} != _FILES):
            raise ValueError("Refusing an unknown or nonprivate synthetic pilot directory.")
        for name in _FILES:
            _regular(path / name)
        return False
    path.mkdir(mode=0o700)  # Parent must already exist; never create arbitrary trees.
    return True


def _tls(directory, now, *, create):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    certfile, keyfile = directory / "localhost.crt", directory / "localhost.key"
    if create:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "LMA synthetic localhost")])
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
        _private_write(certfile, certificate.public_bytes(serialization.Encoding.PEM))
        _private_write(keyfile, key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    else:
        certificate = x509.load_pem_x509_certificate(certfile.read_bytes())
        key = serialization.load_pem_private_key(keyfile.read_bytes(), password=None)
        sans = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if (not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc
                or list(sans) != [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                or certificate.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
                != key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)):
            raise ValueError("The synthetic localhost TLS certificate is invalid.")
    return str(certfile), str(keyfile)


def prepare_runtime(directory, port, issuer, subject, *, vendor_submissions=False):
    """Create a dedicated synthetic database, or reopen its marked private path.

    Existing runtimes receive no schema writes, seeding, grant renewal or role
    repair. Unknown/partial directories fail closed and require manual inspection.
    The application OS account and its private runtime directory remain trusted.
    """
    # This gate precedes src.db imports, filesystem creation and TLS generation.
    if os.getenv("AUTH_MODE") != "development" or os.getenv("DATABASE_URL"):
        raise ValueError("Use AUTH_MODE=development and unset DATABASE_URL for this isolated synthetic pilot.")
    if (type(vendor_submissions) is not bool
            or type(port) is not int or not 1024 <= port <= 65535
            or issuer != f"https://127.0.0.1:{port}/synthetic-idp"
            or subject != "synthetic-analyst"):
        raise ValueError("Use the fixed localhost synthetic analyst identity.")
    path = Path(os.path.abspath(directory))
    if path == Path(path.anchor):
        raise ValueError("Use a dedicated private synthetic pilot directory.")
    now = datetime.now(timezone.utc)
    create = _directory(path)
    expected = dict(format=("lma-synthetic-vendor-runtime-v2" if vendor_submissions
                            else "lma-synthetic-analyst-runtime-v1"), origin=f"https://127.0.0.1:{port}",
                    issuer=issuer, subject=subject)
    if vendor_submissions:
        expected.update(vendor_issuer=f"https://127.0.0.1:{port}/vendor/synthetic-idp",
                        vendor_subject="synthetic-vendor")
    marker = dict(expected, captured_on=now.date().isoformat())
    if not create:
        raw = (path / "runtime.json").read_bytes()
        if not 1 <= len(raw) <= 1024:
            raise ValueError("Invalid synthetic runtime marker.")
        marker = json.loads(raw.decode("ascii"))
        if (type(marker) is not dict or set(marker) != {*expected, "captured_on"}
                or any(marker[key] != value for key, value in expected.items())
                or json.dumps(marker, sort_keys=True, separators=(",", ":")).encode("ascii") != raw):
            raise ValueError("Synthetic runtime origin or format differs.")
        captured = date.fromisoformat(marker["captured_on"])
        if captured.isoformat() != marker["captured_on"] or captured > now.date():
            raise ValueError("Invalid synthetic runtime capture date.")
    certfile, keyfile = _tls(path, now, create=create)

    # Deliberately local imports: production denial cannot initialize a DB engine.
    from sqlalchemy import create_engine, event, inspect, select
    from sqlalchemy.orm import sessionmaker
    from src.db import (Assessment, Base, Engagement, EngagementAccessGrant,
                        Organization, OrganizationMembership, SyntheticAssessmentRevision, SyntheticVendorHandoff,
                        SyntheticEvidenceObject, Vendor)
    from src.organization_methodology import OrganizationMethodology, default_definition
    from src.synthetic_custody_guards import require_synthetic_custody_guards
    from src.synthetic_revision_guards import require_synthetic_revision_guards
    from src.synthetic_handoff_provenance import require_synthetic_handoff_guards
    from src.upload_assessment import Intake

    database = path / "pilot.sqlite"
    if create:
        _private_write(database, b"")
    engine = create_engine("sqlite:///" + str(database), connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def connection_settings(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        if create:
            Base.metadata.create_all(engine)
            with factory.begin() as session:
                session.add(Organization(id=1, external_key="synthetic-pilot", name="Synthetic pilot"))
                session.flush()
                session.add(Vendor(id=11, organization_id=1, legal_name="Synthetic Vendor", display_name="Synthetic Vendor"))
                session.flush()
                session.add(Engagement(id=101, vendor_id=11, service_name="Synthetic Analytics"))
                session.flush()
                session.add(Assessment(id=1001, vendor_id=11, engagement_id=101, assessment_type="Synthetic evidence-first pilot"))
                session.add(OrganizationMembership(id=501, organization_id=1, issuer=issuer, subject=subject,
                    role="Analyst", status="active", valid_from=now - timedelta(minutes=1), expires_at=now + timedelta(days=7)))
                session.flush()
                session.add(EngagementAccessGrant(id=701, membership_id=501, engagement_id=101,
                    status="active", valid_from=now - timedelta(minutes=1), expires_at=now + timedelta(days=7)))
        with engine.connect() as connection:
            if set(inspect(connection).get_table_names()) != set(Base.metadata.tables):
                raise ValueError("The synthetic runtime schema is incomplete or unknown.")
            require_synthetic_custody_guards(connection, SyntheticEvidenceObject.__table__)
            require_synthetic_revision_guards(connection, SyntheticAssessmentRevision.__table__)
            require_synthetic_handoff_guards(connection, SyntheticVendorHandoff.__table__)
        with factory() as session:
            row = session.execute(select(Organization.external_key, Vendor.display_name, Engagement.service_name,
                OrganizationMembership.issuer, OrganizationMembership.subject)
                .select_from(Assessment).join(Engagement, Engagement.id == Assessment.engagement_id)
                .join(Vendor, Vendor.id == Assessment.vendor_id).join(Organization, Organization.id == Vendor.organization_id)
                .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
                .join(EngagementAccessGrant, EngagementAccessGrant.membership_id == OrganizationMembership.id)
                .where(Assessment.id == 1001, Organization.id == 1, Vendor.id == 11, Engagement.id == 101,
                       OrganizationMembership.id == 501, EngagementAccessGrant.id == 701,
                       Engagement.vendor_id == Vendor.id, EngagementAccessGrant.engagement_id == Engagement.id)).one_or_none()
            if row is None or tuple(row) != ("synthetic-pilot", "Synthetic Vendor", "Synthetic Analytics", issuer, subject):
                raise ValueError("The synthetic runtime fixture ownership differs.")
            if vendor_submissions:
                # The independently authenticated vendor receives no SQL
                # membership or grant. Existing analyst/read/custody services
                # therefore confer no tenant authority to that identity.
                vendor_member = session.execute(select(OrganizationMembership.id).where(
                    OrganizationMembership.issuer == expected["vendor_issuer"],
                    OrganizationMembership.subject == expected["vendor_subject"])).first()
                if vendor_member is not None:
                    raise ValueError("The synthetic vendor must have no SQL membership.")
        if create:
            _private_write(path / "runtime.json", json.dumps(marker, sort_keys=True, separators=(",", ":")).encode("ascii"))
        intake = Intake("1001", "Synthetic Vendor", "Synthetic Analytics", "Synthetic analytics assessment",
            as_of=date.fromisoformat(marker["captured_on"]), organization_id="synthetic-pilot",
            methodology=OrganizationMethodology.from_dict(default_definition("synthetic-pilot")))
        return SyntheticPilotRuntime(factory, intake, certfile, keyfile, engine, vendor_submissions)
    except Exception:
        engine.dispose()
        raise
