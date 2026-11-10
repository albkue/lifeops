"""Thin wrapper around the S3-compatible client (MinIO / SeaweedFS / real S3)."""

import logging
from io import BytesIO

from minio import Minio, S3Error

from lifeops_core.config import Settings

logger = logging.getLogger(__name__)


class ObjectNotFoundError(Exception):
    """Raised when an object key does not exist in the bucket."""


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

    def get_object_bytes(self, key: str) -> bytes:
        """Read an object fully; raises ObjectNotFoundError when absent."""
        try:
            response = self._client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
                raise ObjectNotFoundError(key) from exc
            raise

    def object_exists(self, key: str) -> bool:
        try:
            self._client.stat_object(self.bucket, key)
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
                return False
            raise
        return True

    def remove_object(self, key: str) -> None:
        try:
            self._client.remove_object(self.bucket, key)
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject"):
                logger.debug("remove_object: %s already absent", key)
                return
            raise
