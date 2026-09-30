"""Listing photo storage in an S3-compatible bucket (configured via S3_* env vars)."""

from functools import lru_cache

import boto3
from botocore.config import Config

from .config import settings


class StorageNotConfigured(Exception):
    pass


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_key,
        aws_secret_access_key=settings.s3_secret,
        # An empty S3_REGION= line in .env overrides the default with "".
        region_name=settings.s3_region or "us-east-1",
        # Path-style ("<endpoint>/<bucket>/<key>") works on every S3-compatible
        # provider; virtual-host style needs per-bucket DNS that MinIO etc. lack.
        config=Config(s3={"addressing_style": "path"}),
    )


def public_url(key: str) -> str:
    base = settings.s3_public_url or f"{settings.s3_endpoint.rstrip('/')}/{settings.s3_bucket}"
    return f"{base.rstrip('/')}/{key}"


def key_from_url(url: str) -> str | None:
    """The object key behind a URL from public_url(), or None if it isn't ours."""
    prefix = public_url("")
    if not settings.s3_configured or not url.startswith(prefix):
        return None
    return url[len(prefix):] or None


def upload(key: str, data: bytes, content_type: str) -> str:
    """Store `data` under `key` and return its public URL."""
    if not settings.s3_configured:
        raise StorageNotConfigured("S3_ENDPOINT, S3_BUCKET, S3_KEY and S3_SECRET must all be set")
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return public_url(key)


def delete(key: str) -> None:
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)
