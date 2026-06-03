"""Rekognition fast-screen tools: moderation labels + general labels."""
from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config
from strands import tool

from ..settings import get_settings
from ..util.logging import get_logger
from ..util.media import parse_s3_uri
from ..util.tracing import span

log = get_logger(__name__)

# Keep Rekognition calls bounded; rare cross-ocean stalls otherwise pin a pipeline.
# Adaptive retry + big pool so 3 concurrent jurisdictions ×2 API calls each don't starve.
_REK_CFG = Config(connect_timeout=5, read_timeout=20,
                  max_pool_connections=20,
                  retries={"max_attempts": 3, "mode": "adaptive"})


def _rek_client():
    return boto3.client("rekognition", region_name=get_settings().aws_region, config=_REK_CFG)


@tool
def detect_moderation_labels(s3_uri: str, min_confidence: float = 50.0) -> dict[str, Any]:
    """Run Amazon Rekognition moderation label detection on an S3-hosted image.

    Args:
        s3_uri: `s3://bucket/key` pointing at a JPEG/PNG.
        min_confidence: Ignore labels below this confidence (0-100).

    Returns:
        {"labels": [{Name, Confidence, ParentName, TaxonomyLevel}, ...],
         "max_confidence": float, "top_label": str | None}
    """
    bucket, key = parse_s3_uri(s3_uri)
    with span("tool:detect_moderation_labels", s3_uri=s3_uri):
        resp = _rek_client().detect_moderation_labels(
            Image={"S3Object": {"Bucket": bucket, "Name": key}},
            MinConfidence=min_confidence,
        )
    labels = resp.get("ModerationLabels", [])
    max_conf = max((lab["Confidence"] for lab in labels), default=0.0)
    top = max(labels, key=lambda lab: lab["Confidence"], default=None)
    log.info("rekognition moderation", extra={"ctx_s3": s3_uri, "ctx_labels": len(labels), "ctx_max": max_conf})
    return {
        "labels": labels,
        "max_confidence": max_conf,
        "top_label": top["Name"] if top else None,
    }


@tool
def detect_labels(s3_uri: str, max_labels: int = 20, min_confidence: float = 60.0) -> dict[str, Any]:
    """General-purpose Rekognition labels (for modality hints + text detection).

    Returns general labels, whether text/logo is present, and whether any
    label suggests a human is in the scene (used by EU/US child checks).
    """
    bucket, key = parse_s3_uri(s3_uri)
    with span("tool:detect_labels", s3_uri=s3_uri):
        resp = _rek_client().detect_labels(
            Image={"S3Object": {"Bucket": bucket, "Name": key}},
            Features=["GENERAL_LABELS"],
            MaxLabels=max_labels,
            MinConfidence=min_confidence,
        )
    labels = resp.get("Labels", [])
    names = {lab["Name"] for lab in labels}
    has_text = bool(names & {"Text", "Logo", "Poster", "License Plate", "Signage"})
    has_person = bool(names & {"Person", "Human", "Kid", "Baby", "Child", "Teen"})
    return {
        "labels": [{"Name": lab["Name"], "Confidence": lab["Confidence"]} for lab in labels],
        "has_text": has_text,
        "has_person": has_person,
    }
