"""Create a dedicated Bedrock Guardrail for UGC moderation (Hate/Insult/Sexual/Violence/Misconduct)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import boto3

from ugc_moderation.settings import get_settings


NAME = "UGCModerationGuardrail"
CONTENT_POLICY = {
    "filtersConfig": [
        {"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
        {"type": "INSULTS", "inputStrength": "HIGH", "outputStrength": "HIGH"},
        {"type": "SEXUAL", "inputStrength": "HIGH", "outputStrength": "HIGH"},
        {"type": "VIOLENCE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
        {"type": "MISCONDUCT", "inputStrength": "HIGH", "outputStrength": "HIGH"},
        {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"},
    ]
}
SENSITIVE_INFO_POLICY = {
    "piiEntitiesConfig": [
        {"type": "EMAIL", "action": "ANONYMIZE"},
        {"type": "PHONE", "action": "ANONYMIZE"},
        {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCK"},
    ]
}
WORD_POLICY = {
    "managedWordListsConfig": [{"type": "PROFANITY"}],
}


def main() -> int:
    s = get_settings()
    client = boto3.client("bedrock", region_name=s.aws_region)
    resp = client.create_guardrail(
        name=NAME,
        description="UGC multimodal moderation guardrail — demo",
        contentPolicyConfig=CONTENT_POLICY,
        sensitiveInformationPolicyConfig=SENSITIVE_INFO_POLICY,
        wordPolicyConfig=WORD_POLICY,
        blockedInputMessaging="内容被审核规则拦截。",
        blockedOutputsMessaging="内容被审核规则拦截。",
    )
    print("\n=== Guardrail created ===")
    print(f"GUARDRAIL_ID={resp['guardrailId']}")
    print(f"GUARDRAIL_ARN={resp['guardrailArn']}")
    print(f"GUARDRAIL_VERSION=DRAFT (publish a version later if needed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
