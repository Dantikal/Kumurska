"""Хранилище изображений акций и событий (US-17).

Файлы лежат в S3-совместимом хранилище (в dev — MinIO), в базе хранится только ссылка.
"""

import asyncio
from functools import lru_cache
from typing import Protocol

from app.core.config import settings


class StorageError(Exception):
    """Хранилище не приняло файл."""


class ImageStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str:
        """Сохраняет файл и возвращает его публичный URL."""
        ...


class S3ImageStorage:
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        region: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        public_url: str,
    ) -> None:
        import boto3

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self._bucket = bucket
        self._public_url = public_url.rstrip("/")

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            # boto3 синхронный: выносим вызов из event loop
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(type(exc).__name__) from exc
        return f"{self._public_url}/{key}"


class FakeImageStorage:
    """Для тестов: хранит файлы в памяти."""

    def __init__(self, public_url: str = "http://storage.test/content") -> None:
        self.public_url = public_url
        self.files: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        self.files[key] = (data, content_type)
        return f"{self.public_url}/{key}"


@lru_cache
def _s3_storage() -> S3ImageStorage:
    return S3ImageStorage(
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        public_url=settings.s3_public_url,
    )


def get_image_storage() -> ImageStorage:
    """FastAPI-зависимость. Клиент создаётся при первом запросе, в тестах подменяется."""
    return _s3_storage()
