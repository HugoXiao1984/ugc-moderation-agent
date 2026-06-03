"""S3 helpers exposed as Strands tools."""
from __future__ import annotations

import base64
from typing import Any

import boto3
from botocore.config import Config
from strands import tool

from ..settings import get_settings
from ..util.media import image_phash, parse_s3_uri


_S3_CFG = Config(connect_timeout=5, read_timeout=15,
                 max_pool_connections=20,
                 retries={"max_attempts": 3, "mode": "adaptive"})


def _s3():
    return boto3.client("s3", region_name=get_settings().aws_region, config=_S3_CFG)


@tool
def fetch_image_metadata(s3_uri: str) -> dict[str, Any]:
    """Return {size_bytes, content_type, phash} for an image in S3."""
    bucket, key = parse_s3_uri(s3_uri)
    obj = _s3().get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read()
    return {
        "size_bytes": len(body),
        "content_type": obj.get("ContentType", ""),
        "phash": image_phash(body),
        "bucket": bucket,
        "key": key,
    }


@tool
def fetch_image_base64(s3_uri: str) -> str:
    """Return base64 of the S3 image (for debugging / previewing in reports)."""
    bucket, key = parse_s3_uri(s3_uri)
    obj = _s3().get_object(Bucket=bucket, Key=key)
    return base64.b64encode(obj["Body"].read()).decode()


def upload_bytes_to_demo_bucket(data: bytes, key: str, content_type: str = "image/jpeg") -> str:
    """Helper (not a tool) for Streamlit to upload user files."""
    bucket = get_settings().demo_bucket
    _s3().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    return f"s3://{bucket}/{key}"
