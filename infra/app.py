#!/usr/bin/env python3
"""CDK app entry — single stack for the UGC moderation demo cloud deploy."""
from __future__ import annotations

import os

import aws_cdk as cdk

from infra_stack import UgcModerationDemoStack


app = cdk.App()

# Account/region come from the active AWS profile / CDK env.
# Hard-pin us-east-1 because Bedrock + AgentCore resources live there.
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT") or app.node.try_get_context("account"),
    region=os.environ.get("CDK_DEFAULT_REGION") or "us-east-1",
)

UgcModerationDemoStack(
    app,
    "UgcModerationDemo",
    env=env,
    description="UGC Moderation Agent — Demo cloud deploy (FastAPI on Fargate + React on S3/CloudFront, AgentCore Runtime/Memory/Code Interpreter)",
)

app.synth()
