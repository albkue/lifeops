"""Thin wrapper around the MinIO S3-compatible client."""

from io import BytesIO

from minio import Minio

from lifeops_core.config import Settings


class MinioObjectStore:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.bucket = bucket
        self.secure = secure
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "MinioObjectStore":
        return cls(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )

    def bucket_exists(self) -> bool:
        return self._client.bucket_exists(self.bucket)

    def ensure_bucket(self) -> None:
        if not self.bucket_exists():
            self._client.make_bucket(self.bucket)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/json") -> int:
        """Write bytes at `key`; returns byte count."""
        self._client.put_object(
            bucket_name=self.bucket,
            object_name=key,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return len(data)
