"""Deep-review tool: Amazon Nova Pro multimodal understanding.

Sends the image (base64) + jurisdiction hint and asks Nova to produce a
structured JSON verdict with Chinese reasoning.
"""
from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.config import Config
from strands import tool

from ..settings import get_settings
from ..util.logging import get_logger
from ..util.media import parse_s3_uri, resize_for_nova
from ..util.tracing import span

log = get_logger(__name__)

_NOVA_SYSTEM = """你是一位多模态内容审核专家。请从下列法域视角审视图像：{jurisdiction}。
结合图像内容和文字提示判断是否违规，输出严格 JSON，字段：
- risk_tags: 细粒度风险标签数组
- verdict: allow | deny | human_review
- confidence: 0~1 小数
- reasoning_cn: 简洁中文理由（2~4 句，可直接展示给运营）
- ocr_text: 图中识别到的文字拼接（没有则空串）
只输出 JSON，不要包含解释或 Markdown。"""

# Bounded timeouts + adaptive retry + a larger connection pool so concurrent
# jurisdiction/batch requests don't starve on the default pool size of 10.
_S3_CFG = Config(connect_timeout=5, read_timeout=15,
                 max_pool_connections=20,
                 retries={"max_attempts": 3, "mode": "adaptive"})
_BEDROCK_CFG = Config(connect_timeout=10, read_timeout=60,
                      max_pool_connections=20,
                      retries={"max_attempts": 3, "mode": "adaptive"})


def _bedrock():
    return boto3.client("bedrock-runtime", region_name=get_settings().aws_region, config=_BEDROCK_CFG)


def _s3():
    return boto3.client("s3", region_name=get_settings().aws_region, config=_S3_CFG)


def _fetch(s3_uri: str) -> bytes:
    bucket, key = parse_s3_uri(s3_uri)
    obj = _s3().get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()


@tool
def analyze_with_nova(
    s3_uri: str,
    jurisdiction: str,
    hint: str = "",
    image_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Invoke Nova Pro on an image with a jurisdiction-aware prompt.

    Args:
        s3_uri: `s3://bucket/key` of the image — used for S3 GetObject only if
                image_bytes is None.
        jurisdiction: CN | EU | US.
        hint: Orchestrator hint (prior risk, detected labels).
        image_bytes: Optional pre-fetched JPEG-ready bytes. When provided we
                     skip the S3 round-trip entirely (used by hybrid pipeline
                     to avoid duplicate fetches over flaky cross-region links).

    Returns:
        Parsed JSON dict (see _NOVA_SYSTEM fields). Falls back to safe allow
        with low confidence if Nova fails to produce valid JSON.
    """
    settings = get_settings()
    if image_bytes is None:
        with span("tool:nova.fetch+resize", s3_uri=s3_uri):
            image_bytes = resize_for_nova(_fetch(s3_uri))
    else:
        # Bytes were pre-fetched + pre-resized upstream; nothing to do.
        with span("tool:nova.reuse_bytes", size_bytes=len(image_bytes)):
            pass

    user_text = f"请审核这张图像。编排侧提示: {hint}" if hint else "请审核这张图像。"

    system = [{"text": _NOVA_SYSTEM.format(jurisdiction=jurisdiction)}]
    messages = [
        {
            "role": "user",
            "content": [
                {"image": {"format": "jpeg", "source": {"bytes": image_bytes}}},
                {"text": user_text},
            ],
        }
    ]

    with span("tool:nova.converse", model=settings.nova_model_id, jurisdiction=jurisdiction):
        resp = _bedrock().converse(
            modelId=settings.nova_model_id,
            system=system,
            messages=messages,
            inferenceConfig={"maxTokens": 512, "temperature": 0.1},
        )
    text = resp["output"]["message"]["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log.warning("nova returned non-json", extra={"ctx_raw": text[:300]})
        parsed = {
            "risk_tags": [],
            "verdict": "human_review",
            "confidence": 0.3,
            "reasoning_cn": f"Nova 深度审核返回的格式无法解析，转人审。原文: {text[:120]}",
            "ocr_text": "",
        }

    parsed.setdefault("ocr_text", "")
    return parsed
