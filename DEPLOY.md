# Deploy to AWS — Demo 部署手册

把 UGC Moderation Agent 整体部署到 AWS（us-east-1）：
- 前端 React → S3 + CloudFront
- 后端 FastAPI → ECS Fargate (arm64) + ALB
- AgentCore Runtime / Memory / Code Interpreter / Guardrail 复用现有资源
- IaC 全部 AWS CDK (Python)

架构详见 [docs/architecture-cloud.md](docs/architecture-cloud.md)。

---

## 0. 前置依赖

```bash
# AWS CLI 已配好，profile 指向 us-east-1，账号 ID 与 .bedrock_agentcore.yaml 一致
aws sts get-caller-identity

# Node.js 20+ / npm（前端构建）
node -v
npm -v

# Python 3.11/3.12（CDK）
python3 --version

# CDK CLI
npm install -g aws-cdk@2
cdk --version

# Docker（CDK 构建镜像用）
docker --version
docker buildx ls    # 必须支持 linux/arm64

# macOS 上如果没装 buildx：
# docker buildx create --use --name multiarch
```

如果在 Apple Silicon 上构建 arm64 → 原生 build；x86 主机上要装 binfmt：

```bash
docker run --privileged --rm tonistiigi/binfmt --install all
```

---

## 1. 创建 / 沿用 AgentCore 资源（一次性）

项目里已经跑过这几个脚本，资源 ID 写在 `.env` 里。如果是干净环境：

```bash
cd /Users/hugoxiao/ugc-moderation-agent
uv sync
cp .env.example .env

uv run python scripts/create_memory.py            # → MEMORY_ID
uv run python scripts/create_guardrail.py         # → GUARDRAIL_ID
uv run python scripts/create_code_interpreter.py  # → CODE_INTERPRETER_ID

# 把 AgentCore Runtime ARN 也准备好（已部署过：见 .bedrock_agentcore.yaml 的 agent_arn）
# 没部署的话：agentcore configure --entrypoint src/ugc_moderation/app.py && agentcore launch
```

把 4 个 ID/ARN 写进 SSM Parameter Store（CDK 会从这里读）：

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

# 从 .env 读出来后塞进 SSM
source .env

aws ssm put-parameter --region $REGION --type String --overwrite \
  --name /ugc-moderation/MEMORY_ID --value "$MEMORY_ID"

aws ssm put-parameter --region $REGION --type String --overwrite \
  --name /ugc-moderation/GUARDRAIL_ID --value "$GUARDRAIL_ID"

aws ssm put-parameter --region $REGION --type String --overwrite \
  --name /ugc-moderation/CODE_INTERPRETER_ID --value "$CODE_INTERPRETER_ID"

# AgentCore Runtime ARN 从 .bedrock_agentcore.yaml 拿（agent_arn 字段）
aws ssm put-parameter --region $REGION --type String --overwrite \
  --name /ugc-moderation/AGENT_RUNTIME_ARN \
  --value "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/<RUNTIME_NAME>"
```

---

## 2. 构建前端 dist/

CDK 会从 `ui/dist/` 上传到 S3，必须先构建：

```bash
cd ui
npm install
npm run build       # 产物在 ui/dist/
cd ..
```

> 前端代码里 `BASE = ""` → 直接调 `/api/...`；CloudFront 会把 `/api/*` 路由到 ALB，不用配置环境变量。

---

## 3. 部署 CDK Stack

```bash
cd infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 第一次需要 bootstrap（每个 account/region 一次性）
cdk bootstrap aws://${ACCOUNT}/us-east-1

# 看看会创建什么
cdk synth

# 部署（首次构建镜像 + 推 ECR + 起 Fargate ≈ 8-12 min）
# 默认会新建 VPC（含 1 个 NAT）
cdk deploy

# 如果想复用现有 VPC（要求至少 2 个 AZ + 1 个 NAT）：
cdk deploy -c vpc_id=vpc-xxxxxxxxxxxxxxxxx
```

部署完会输出：

```
UgcModerationDemo.CloudFrontUrl   = https://dxxxxxx.cloudfront.net
UgcModerationDemo.AlbDnsName      = UgcMod-Backe-XXXX.us-east-1.elb.amazonaws.com
UgcModerationDemo.UgcBucketName   = ugcmoderationdemo-ugcbucket-xxxxxx
UgcModerationDemo.SiteBucketName  = ugcmoderationdemo-sitebucket-xxxxxx
UgcModerationDemo.EcrRepoUri      = <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/cdk-...
```

打开 `CloudFrontUrl` → 看到 React 界面 → 上传图片 → 走通 = 部署成功。

---

## 4. 验证

```bash
# 健康检查（直连 ALB）
curl http://${ALB_DNS}/api/health

# 通过 CloudFront
curl https://${CF_DOMAIN}/api/health
curl https://${CF_DOMAIN}/api/meta
```

后端日志：

```bash
aws logs tail /aws/ecs/UgcModerationDemo-BackendLogs --follow --region us-east-1
```

如果视频任务跑不动，先看：
- ECS 任务有没有起来：`aws ecs list-tasks --cluster UgcModerationDemo-Cluster`
- AgentCore Runtime 调用权限是否到位（IAM 角色 `UgcModerationDemo-BackendTaskRole...`）
- SSM 参数是否真的有值：`aws ssm get-parameter --name /ugc-moderation/MEMORY_ID`

---

## 5. 后续更新

**只改了后端代码：**
```bash
cd infra && cdk deploy   # 自动重 build 镜像并 rolling update
```

**只改了前端：**
```bash
cd ui && npm run build && cd ..
cd infra && cdk deploy   # BucketDeployment 会同步 + 自动 invalidate /*
```

**只改了 AgentCore Memory ID（换了一组）：**
```bash
aws ssm put-parameter --overwrite --name /ugc-moderation/MEMORY_ID --value <NEW_ID>
aws ecs update-service --cluster ... --service ... --force-new-deployment
```

---

## 6. 收摊（演示完）

**临时省钱（保留所有数据）：**
```bash
aws ecs update-service --cluster UgcModerationDemo-Cluster \
  --service <service-name> --desired-count 0
```

**彻底拆掉：**
```bash
cd infra && cdk destroy
```

> 注意 UGC bucket 设了 `auto_delete_objects=True`，里面所有用户上传的内容会被一起删掉。

---

## 故障排查清单

| 现象 | 排查点 |
|---|---|
| 前端打开 403 | CloudFront 缓存没失效 → 控制台手动 invalidation `/*` |
| `/api/*` 502/504 | ALB target 不健康 → ECS task 起来没？看 CW Logs；视频任务超 idle → ALB idle 已设 300s 仍不够则提工单 |
| Bedrock AccessDenied | task role 缺权限 → 看 stack 里 `BackendTaskRole` 策略 |
| AgentCore 调用 ResourceNotFoundException | SSM 里的 `AGENT_RUNTIME_ARN` 不对，或 Runtime 没 deploy |
| 镜像构建报 `exec format error` | host 不是 arm64，没装 binfmt → 见前置依赖 |
| `cdk deploy` 卡在 BucketDeployment | `ui/dist/` 不存在 → 先 `cd ui && npm run build` |
