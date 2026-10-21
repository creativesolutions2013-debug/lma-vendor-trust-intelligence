import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


DEFAULT_LOCAL_STORAGE_DIR = "uploaded_evidence"


def validate_evidence_key(key: str, *, vendor_id: Optional[int] = None) -> str:
    """Validate an opaque vendor-scoped object key, without filesystem access.

    Keys are never decoded or normalized: URL encodings, alternate separators,
    absolute paths and noncanonical IDs cannot acquire a different meaning later.
    A vendor prefix is an association check, not relationship authorization.
    """
    if (not isinstance(key, str) or not re.fullmatch(
            r"vendors/([1-9][0-9]*)/evidence/[A-Za-z0-9_-][A-Za-z0-9._-]{0,254}", key)):
        raise ValueError("Invalid vendor-scoped evidence key.")
    if vendor_id is not None:
        if type(vendor_id) is not int or vendor_id < 1 or key.split("/")[1] != str(vendor_id):
            raise ValueError("Evidence key does not match the expected vendor.")
    return key


def _safe_filename(filename: str) -> str:
    """Return a filesystem/object-store-safe filename."""
    name = Path(filename or "evidence.bin").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or "evidence.bin"


def build_evidence_key(
    vendor_id: int,
    filename: str,
    *,
    unique_id: Optional[str] = None,
) -> str:
    """
    Create a collision-resistant evidence-storage key.

    Uploaded filenames are sanitized and scoped to the vendor.
    """
    if type(vendor_id) is not int or vendor_id < 1:
        raise ValueError("A positive integer vendor ID is required.")
    token = uuid.uuid4().hex if unique_id is None else unique_id
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", token):
        raise ValueError("A safe opaque evidence ID is required.")
    safe_name = _safe_filename(filename)

    return validate_evidence_key(
        f"vendors/{vendor_id}/evidence/"
        f"{token}_{safe_name}"
    )


class LocalEvidenceStorage:
    """
    Development evidence-storage backend.

    Files are written to the local filesystem. This remains the
    default backend for the MVP and local development.
    """

    def __init__(
        self,
        base_dir: str = DEFAULT_LOCAL_STORAGE_DIR,
    ):
        # Pin relative configuration to this working directory without following
        # links. Initialization itself never creates or reads the storage tree.
        self.base_dir = Path(os.path.abspath(base_dir))
        if self.base_dir == Path(self.base_dir.anchor):
            raise ValueError("Use a dedicated evidence-storage directory.")

    @contextmanager
    def _parent(self, key: str, *, create: bool, vendor_id: Optional[int]):
        """Walk from / using directory descriptors; never follow any symlink.

        POSIX no-follow/dir_fd support is required rather than an unsafe fallback.
        An open parent stays anchored if a symlink is substituted after checking.
        The configured tree must still be private to the application OS account;
        this is not isolation from a hostile process with the same filesystem rights.
        """
        validate_evidence_key(key, vendor_id=vendor_id)
        if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
                or any(fn not in os.supports_dir_fd for fn in (os.open, os.mkdir, os.stat, os.unlink))):
            raise RuntimeError("Secure local storage requires directory-relative no-follow support.")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open(self.base_dir.anchor, flags)
        try:
            for part in self.base_dir.parts[1:] + tuple(key.split("/")[:-1]):
                try:
                    child = os.open(part, flags, dir_fd=descriptor)
                except FileNotFoundError:
                    if not create:
                        yield None, key.split("/")[-1]
                        return
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass  # Reopen with O_NOFOLLOW even after a concurrent create.
                    child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            yield descriptor, key.split("/")[-1]
        except OSError as exc:
            # Do not turn unsafe paths into an innocuous "not present" result.
            raise ValueError("Unsafe or inaccessible local evidence path.") from exc
        finally:
            os.close(descriptor)

    @staticmethod
    def _regular_file(metadata):
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("Evidence must be a regular file without links.")

    def _leaf(self, parent, leaf):
        try:
            metadata = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return False
        self._regular_file(metadata)
        return True

    def save(
        self,
        key: str,
        content: bytes,
        *,
        vendor_id: Optional[int] = None,
    ) -> str:
        validate_evidence_key(key, vendor_id=vendor_id)
        if not isinstance(content, bytes):
            raise ValueError("Evidence content must be bytes.")
        with self._parent(key, create=True, vendor_id=vendor_id) as (parent, leaf):
            self._leaf(parent, leaf)
            descriptor = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 mode=0o600, dir_fd=parent)
            with os.fdopen(descriptor, "wb") as target:
                self._regular_file(os.fstat(target.fileno()))
                target.truncate(0)
                target.write(content)
        return str(self.base_dir / key)

    def exists(
        self,
        key: str,
        *,
        vendor_id: Optional[int] = None,
    ) -> bool:
        with self._parent(key, create=False, vendor_id=vendor_id) as (parent, leaf):
            return parent is not None and self._leaf(parent, leaf)

    def delete(
        self,
        key: str,
        *,
        vendor_id: Optional[int] = None,
    ) -> None:
        with self._parent(key, create=False, vendor_id=vendor_id) as (parent, leaf):
            if parent is not None and self._leaf(parent, leaf):
                try:
                    os.unlink(leaf, dir_fd=parent)
                except FileNotFoundError:
                    pass


class S3EvidenceStorage:
    """
    Durable evidence-storage backend using S3 or an
    S3-compatible object-storage service.
    """

    def __init__(
        self,
        bucket: str,
        *,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        if not bucket:
            raise ValueError(
                "S3 bucket is required."
            )

        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required when "
                "STORAGE_BACKEND=s3."
            ) from exc

        self.bucket = bucket

        self.client = boto3.client(
            "s3",
            region_name=region or None,
            endpoint_url=endpoint_url or None,
        )

    def save(
        self,
        key: str,
        content: bytes,
    ) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ServerSideEncryption="AES256",
        )

        return f"s3://{self.bucket}/{key}"

    def exists(
        self,
        key: str,
    ) -> bool:
        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=key,
            )

            return True

        except self.client.exceptions.ClientError as exc:
            status = (
                exc.response
                .get("ResponseMetadata", {})
                .get("HTTPStatusCode")
            )

            if status == 404:
                return False

            raise

    def delete(
        self,
        key: str,
    ) -> None:
        self.client.delete_object(
            Bucket=self.bucket,
            Key=key,
        )


def get_evidence_storage():
    """
    Return the configured evidence-storage backend.

    Local development defaults:

        STORAGE_BACKEND=local
        EVIDENCE_LOCAL_DIR=uploaded_evidence

    Production S3 configuration:

        STORAGE_BACKEND=s3
        EVIDENCE_S3_BUCKET=<bucket>
        AWS_REGION=<region>

    Optional for S3-compatible services:

        EVIDENCE_S3_ENDPOINT_URL=<endpoint>
    """
    backend = os.getenv(
        "STORAGE_BACKEND",
        "local",
    ).strip().lower()

    if backend == "local":
        return LocalEvidenceStorage(
            os.getenv(
                "EVIDENCE_LOCAL_DIR",
                DEFAULT_LOCAL_STORAGE_DIR,
            )
        )

    if backend == "s3":
        return S3EvidenceStorage(
            bucket=os.getenv(
                "EVIDENCE_S3_BUCKET",
                "",
            ),
            region=os.getenv(
                "AWS_REGION"
            ),
            endpoint_url=os.getenv(
                "EVIDENCE_S3_ENDPOINT_URL"
            ),
        )

    raise ValueError(
        "Unsupported STORAGE_BACKEND. "
        "Expected 'local' or 's3'."
    )
