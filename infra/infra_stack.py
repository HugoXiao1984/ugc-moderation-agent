"""UGC Moderation Demo — single CDK stack.

布局：
  浏览器
    ├─ CloudFront ── S3 (静态前端，默认行为)
    └─ CloudFront ── ALB ── ECS Fargate (FastAPI)         (/api/* 行为)
                              │
                              ├─ AgentCore Runtime (已存在，按 ARN 调用)
                              ├─ AgentCore Memory / Code Interpreter / Guardrail
                              ├─ Bedrock (Nova / Sonnet / Haiku) + Rekognition
                              └─ S3 (UGC bucket，存上传内容)

CloudFront 单分发双源 → 一个域名搞定，前端直接调 /api/* 不用配 CORS。
"""
from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_ssm as ssm,
)
from constructs import Construct


REPO_ROOT = Path(__file__).resolve().parent.parent


class UgcModerationDemoStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------
        # 1) 配置参数（从 SSM 读，避免把 ID 硬塞进代码 / 镜像）
        #    部署前先在 Parameter Store 创建好这几条（见 DEPLOY.md）：
        #      /ugc-moderation/MEMORY_ID
        #      /ugc-moderation/GUARDRAIL_ID
        #      /ugc-moderation/CODE_INTERPRETER_ID
        #      /ugc-moderation/AGENT_RUNTIME_ARN   (可选；置空 = 后端走本地 in-process Graph)
        # ------------------------------------------------------------------
        param_path = "/ugc-moderation"

        # ------------------------------------------------------------------
        # 2) UGC bucket — 用户上传的图片/视频
        # ------------------------------------------------------------------
        ugc_bucket = s3.Bucket(
            self,
            "UgcBucket",
            bucket_name=None,  # 让 CDK 自动起带 hash 的名字，避免冲突
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.GET, s3.HttpMethods.HEAD],
                    allowed_origins=["*"],  # presigned URL 自带签名，allow * 是常规做法
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="expire-demo-uploads",
                    enabled=True,
                    prefix="uploads/",            # 只清临时上传；samples/ 永久保留
                    expiration=Duration.days(7),  # Demo 内容 7 天清掉，不留垃圾
                )
            ],
        )

        # ------------------------------------------------------------------
        # 3) 前端静态站 bucket（CloudFront 默认源）
        #    用 OAC，让 bucket 保持完全私有
        # ------------------------------------------------------------------
        site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # ------------------------------------------------------------------
        # 4) VPC + ECS Cluster + Fargate (FastAPI 后端)
        #
        # 两种模式：
        #   - 不传 -c vpc_id=...           → 新建 VPC（max_azs=2, nat_gateways=1）
        #   - 传 -c vpc_id=vpc-xxxxxxxx    → 复用现有 VPC（要求至少 2 AZ + 1 NAT）
        #
        # 例：
        #   cdk deploy -c vpc_id=vpc-0123456789abcdef0
        # ------------------------------------------------------------------
        existing_vpc_id = self.node.try_get_context("vpc_id")
        if existing_vpc_id:
            vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_id=existing_vpc_id)
        else:
            vpc = ec2.Vpc(
                self,
                "Vpc",
                max_azs=2,
                nat_gateways=1,  # Demo 单 NAT 省钱（生产建议 2）
            )

        cluster = ecs.Cluster(self, "Cluster", vpc=vpc, container_insights=True)

        # Docker image — CDK 会用本地 buildx 构建并推到 CDK 自动管理的 ECR。
        # platform 显式 linux/arm64 与 .bedrock_agentcore.yaml 保持一致。
        backend_image = ecr_assets.DockerImageAsset(
            self,
            "BackendImage",
            directory=str(REPO_ROOT),
            platform=ecr_assets.Platform.LINUX_ARM64,
            # ECS web server uses Dockerfile.web; the root Dockerfile is the
            # AgentCore Runtime contract (built by CodeBuild for the Runtime).
            file="Dockerfile.web",
        )

        log_group = logs.LogGroup(
            self,
            "BackendLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Task role — 应用调 AWS API 时用的身份
        task_role = iam.Role(
            self,
            "BackendTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # Bedrock 调模型 + Rekognition + Bedrock Agent (AgentCore)
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:ApplyGuardrail",
                ],
                resources=["*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "rekognition:DetectModerationLabels",
                    "rekognition:DetectLabels",
                    "rekognition:DetectText",
                    "rekognition:DetectFaces",
                ],
                resources=["*"],
            )
        )
        # AgentCore Runtime / Memory / Code Interpreter
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:CreateMemoryRecord",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:UpdateMemoryRecord",
                    "bedrock-agentcore:DeleteMemoryRecord",
                    "bedrock-agentcore:ListMemoryRecords",
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:StartCodeInterpreterSession",
                    "bedrock-agentcore:StopCodeInterpreterSession",
                    "bedrock-agentcore:InvokeCodeInterpreter",
                    "bedrock-agentcore:GetCodeInterpreterSession",
                ],
                resources=["*"],
            )
        )
        # SSM 参数读取
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter{param_path}/*",
                ],
            )
        )
        # UGC bucket 读写
        ugc_bucket.grant_read_write(task_role)

        # ------------------------------------------------------------------
        # 5) ApplicationLoadBalancedFargateService
        #    internet-facing ALB（CloudFront 也能回源到 internal 的 VPC origin，
        #    但内部 Demo 用 internet-facing 配置最简单 + 成本一致）。
        # ------------------------------------------------------------------
        fargate = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Backend",
            cluster=cluster,
            cpu=1024,
            memory_limit_mib=2048,
            desired_count=1,
            public_load_balancer=True,
            assign_public_ip=False,
            runtime_platform=ecs.RuntimePlatform(
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
                cpu_architecture=ecs.CpuArchitecture.ARM64,
            ),
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_docker_image_asset(backend_image),
                container_port=8000,
                task_role=task_role,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="backend",
                    log_group=log_group,
                ),
                environment={
                    "AWS_REGION": self.region,
                    "DEMO_BUCKET": ugc_bucket.bucket_name,
                    "PIPELINE_MODE": "hybrid",  # 生产推荐版本
                    "CLIENT_MODE": "remote",    # 优先调远程 AgentCore Runtime
                },
                secrets={
                    "MEMORY_ID": ecs.Secret.from_ssm_parameter(
                        ssm.StringParameter.from_string_parameter_name(
                            self, "MemoryIdParam", string_parameter_name=f"{param_path}/MEMORY_ID"
                        )
                    ),
                    "GUARDRAIL_ID": ecs.Secret.from_ssm_parameter(
                        ssm.StringParameter.from_string_parameter_name(
                            self, "GuardrailIdParam", string_parameter_name=f"{param_path}/GUARDRAIL_ID"
                        )
                    ),
                    "CODE_INTERPRETER_ID": ecs.Secret.from_ssm_parameter(
                        ssm.StringParameter.from_string_parameter_name(
                            self, "CodeInterpreterIdParam",
                            string_parameter_name=f"{param_path}/CODE_INTERPRETER_ID",
                        )
                    ),
                    "AGENT_RUNTIME_ARN": ecs.Secret.from_ssm_parameter(
                        ssm.StringParameter.from_string_parameter_name(
                            self, "AgentRuntimeArnParam",
                            string_parameter_name=f"{param_path}/AGENT_RUNTIME_ARN",
                        )
                    ),
                },
            ),
            health_check_grace_period=Duration.seconds(60),
        )

        # 健康检查打到 FastAPI 自带的 /api/health
        fargate.target_group.configure_health_check(
            path="/api/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
        )
        # 视频任务可能跑几分钟，把 idle timeout 拉长
        fargate.load_balancer.set_attribute("idle_timeout.timeout_seconds", "300")

        # ------------------------------------------------------------------
        # 6) CloudFront — 单分发双源
        # ------------------------------------------------------------------
        # 默认源：私有 S3 + OAC
        s3_origin = origins.S3BucketOrigin.with_origin_access_control(site_bucket)

        # /api/* 源：internet-facing ALB（HTTP only）
        # 视频审核是同步接口，处理时间随帧数线性增长（1 帧/秒，90s 视频可达
        # ~75s+）。CloudFront → 源的 read_timeout 默认 30s 会在视频跑完前切断
        # 连接返回 504。read_timeout 提到 120s（CloudFront 配额内最大，>120 才
        # 需提工单）以覆盖视频处理时长。keepalive 只影响连接复用、不影响请求
        # 超时；此 CDK 版本校验上限 180s，设满即可（AWS API 本身允许到 300s）。
        alb_origin = origins.LoadBalancerV2Origin(
            fargate.load_balancer,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            http_port=80,
            read_timeout=Duration.seconds(120),
            keepalive_timeout=Duration.seconds(180),
        )

        distribution = cloudfront.Distribution(
            self,
            "Cdn",
            comment="UGC Moderation Demo",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=s3_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                compress=True,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=alb_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                    compress=False,
                ),
            },
            error_responses=[
                # SPA 路由兜底
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,  # NA + EU，便宜
        )

        # ------------------------------------------------------------------
        # 7) 把构建好的前端 dist/ 上传到 S3 并自动失效 CloudFront 缓存
        #    部署前需要先 cd ui && npm run build。
        # ------------------------------------------------------------------
        ui_dist = REPO_ROOT / "ui" / "dist"
        if ui_dist.exists():
            s3deploy.BucketDeployment(
                self,
                "DeploySite",
                sources=[s3deploy.Source.asset(str(ui_dist))],
                destination_bucket=site_bucket,
                distribution=distribution,
                distribution_paths=["/*"],
                prune=True,
            )

        # ------------------------------------------------------------------
        # 8) Outputs
        # ------------------------------------------------------------------
        cdk.CfnOutput(self, "CloudFrontUrl",
                      value=f"https://{distribution.distribution_domain_name}",
                      description="演示入口 URL")
        cdk.CfnOutput(self, "AlbDnsName",
                      value=fargate.load_balancer.load_balancer_dns_name,
                      description="后端 ALB（调试用，正常通过 CloudFront 访问）")
        cdk.CfnOutput(self, "UgcBucketName",
                      value=ugc_bucket.bucket_name,
                      description="UGC 上传 bucket（前端 presigned URL 直传到这里）")
        cdk.CfnOutput(self, "SiteBucketName",
                      value=site_bucket.bucket_name,
                      description="前端静态站 bucket")
        cdk.CfnOutput(self, "EcrRepoUri",
                      value=backend_image.repository.repository_uri,
                      description="后端镜像 ECR 仓库")
