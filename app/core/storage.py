import mimetypes
from io import BytesIO
from pathlib import Path

from minio import Minio

from app.core.config import settings


def get_minio_client() -> Minio:
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket_exists() -> None:
    client = get_minio_client()
    found = client.bucket_exists(settings.minio_bucket)
    if not found:
        client.make_bucket(settings.minio_bucket)


def upload_file_to_minio(local_path: str | Path, object_name: str) -> str:
    local_path = Path(local_path)
    if not local_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {local_path}")

    client = get_minio_client()
    ensure_bucket_exists()

    content_type, _ = mimetypes.guess_type(local_path.name)
    client.fput_object(
        bucket_name=settings.minio_bucket,
        object_name=object_name,
        file_path=str(local_path),
        content_type=content_type or "application/octet-stream",
    )
    return object_name


def download_object_bytes(object_name: str) -> bytes:
    """Read a private artifact from MinIO and release its HTTP connection."""
    response = get_minio_client().get_object(settings.minio_bucket, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def upload_object_bytes(data: bytes, object_name: str, content_type: str) -> str:
    """Store a generated image artifact under a stable object name."""
    ensure_bucket_exists()
    get_minio_client().put_object(
        bucket_name=settings.minio_bucket,
        object_name=object_name,
        data=BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name
