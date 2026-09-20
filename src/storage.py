import os
import re
import uuid
from pathlib import Path
from typing import Optional


DEFAULT_LOCAL_STORAGE_DIR = "uploaded_evidence"


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
    token = unique_id or uuid.uuid4().hex
    safe_name = _safe_filename(filename)

    return (
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
        self.base_dir = Path(base_dir)

    def save(
        self,
        key: str,
        content: bytes,
    ) -> str:
        destination = self.base_dir / key
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_bytes(content)

        return str(destination)

    def exists(
        self,
        key: str,
    ) -> bool:
        return (self.base_dir / key).exists()

    def delete(
        self,
        key: str,
    ) -> None:
        path = self.base_dir / key

        if path.exists():
            path.unlink()


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