"""Create a dedicated AgentCore Code Interpreter resource for jurisdiction scripts."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import boto3

from ugc_moderation.settings import get_settings


def main() -> int:
    s = get_settings()
    client = boto3.client("bedrock-agentcore-control", region_name=s.aws_region)
    try:
        resp = client.create_code_interpreter(
            name="UGCModerationPolicyCI",
            description="Sandbox for cn/eu/us jurisdiction policy scripts",
            networkConfiguration={"networkMode": "SANDBOX"},
        )
    except client.exceptions.ConflictException:
        existing = client.list_code_interpreters()
        for ci in existing.get("codeInterpreterSummaries", []):
            if ci.get("name") == "UGCModerationPolicyCI":
                resp = ci
                break
        else:
            raise

    ci_id = resp.get("codeInterpreterId") or resp.get("id")
    print("\n=== Code Interpreter ===")
    print(f"CODE_INTERPRETER_ID={ci_id}")
    print("(Leave blank to use AWS default interpreter; our tool falls back automatically.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
