# Cloud Architecture — UGC Moderation Demo

> 部署目标：客户 Demo / POC，单 region (us-east-1)，前后端全部上 AWS。
> AgentCore 三件套（Runtime / Memory / Code Interpreter）+ Guardrail 是核心，下图用**紫色高亮**。

## 全局视图

```mermaid
flowchart TB
    classDef agentcore fill:#7c3aed,stroke:#4c1d95,color:#fff,stroke-width:2px
    classDef bedrock fill:#0ea5e9,stroke:#0369a1,color:#fff
    classDef edge fill:#f59e0b,stroke:#b45309,color:#111
    classDef compute fill:#16a34a,stroke:#14532d,color:#fff
    classDef storage fill:#64748b,stroke:#1e293b,color:#fff
    classDef user fill:#fde68a,stroke:#92400e,color:#111

    User([👤 用户浏览器]):::user

    subgraph Edge["边缘 / 静态托管"]
      direction TB
      CF[CloudFront<br/>单分发双源]:::edge
      Site[(S3<br/>React SPA<br/>静态文件)]:::storage
    end

    subgraph Net["VPC (us-east-1, 2 AZ)"]
      direction TB
      ALB[Application Load Balancer<br/>internet-facing<br/>idle 300s]:::edge
      subgraph ECS["ECS Fargate · arm64 · 1 task"]
        API[FastAPI · uvicorn<br/>backend.api:app<br/>BackgroundTasks 跑视频]:::compute
      end
    end

    subgraph DataPlane["数据面"]
      direction TB
      UGC[(S3<br/>UGC bucket<br/>presigned 直传<br/>7 天过期)]:::storage
      SSM[(SSM Parameter Store<br/>MEMORY_ID / GUARDRAIL_ID<br/>CODE_INTERPRETER_ID<br/>AGENT_RUNTIME_ARN)]:::storage
      ECR[(ECR<br/>backend image)]:::storage
    end

    subgraph BedrockAgentCore["🟣 Amazon Bedrock AgentCore（演示核心 — 高亮）"]
      direction TB
      Runtime["AgentCore Runtime<br/>Firecracker microVM<br/>每会话隔离<br/>合规可审计"]:::agentcore
      Memory["AgentCore Memory<br/>误判记忆 / 召回相似案例<br/>命名空间按租户隔离"]:::agentcore
      CodeInterp["AgentCore Code Interpreter<br/>热执行 cn/eu/us.py<br/>改规则不改 Agent 代码"]:::agentcore
    end

    subgraph BedrockModels["Bedrock 模型层"]
      direction TB
      Guardrail["Bedrock Guardrail<br/>文本护栏 ④"]:::bedrock
      Nova["Nova Pro<br/>多模态深度审核 ②"]:::bedrock
      Sonnet["Claude Sonnet 4.6<br/>decision_heavy<br/>中文推理"]:::bedrock
      Haiku["Claude Haiku 4.5<br/>orchestrator / fast / decision_light"]:::bedrock
      Rek["Amazon Rekognition<br/>快筛 ①"]:::bedrock
    end

    User -- "https (HTML/JS/CSS)" --> CF
    CF -- "默认行为 /*" --> Site
    User -- "https /api/*" --> CF
    CF -- "回源 /api/*" --> ALB
    ALB --> API

    API -- "presigned PUT/GET" --> UGC
    User -. "PUT 直传 (presigned)" .-> UGC

    API -- "InvokeAgentRuntime<br/>(payload: s3_uri + jurisdiction)" --> Runtime
    API -. "本地降级模式<br/>CLIENT_MODE=local" .- Haiku
    API -- "读取配置" --> SSM
    ECR -. "镜像拉取" .- ECS

    Runtime -- "编排 5 节点 Graph" --> Rek
    Runtime --> Nova
    Runtime --> Guardrail
    Runtime --> Memory
    Runtime --> CodeInterp
    Runtime --> Haiku
    Runtime --> Sonnet
    CodeInterp -. "热加载 policies_scripts/" .- UGC
```

## AgentCore 组件在请求路径中的位置

```mermaid
sequenceDiagram
    autonumber
    participant U as 浏览器
    participant CF as CloudFront
    participant API as FastAPI (Fargate)
    participant S3 as S3 (UGC)
    participant RT as 🟣 AgentCore Runtime
    participant MEM as 🟣 AgentCore Memory
    participant CI as 🟣 AgentCore Code Interpreter
    participant BR as Bedrock 模型 (Rek/Nova/Guardrail/Haiku/Sonnet)

    U->>CF: GET /index.html
    CF->>U: SPA bundle (S3 origin)
    U->>CF: POST /api/upload (small) or<br/>GET /api/presign (large)
    CF->>API: forward to ALB → Fargate
    API->>S3: PUT object / 返回 presigned URL
    U->>S3: PUT 大文件直传 (跨过后端)
    U->>CF: POST /api/moderate { s3_uri, jurisdiction }
    CF->>API: forward
    API->>RT: InvokeAgentRuntime (microVM 启动)
    RT->>MEM: 召回相似案例 (按租户命名空间)
    MEM-->>RT: 历史误判 + 阈值建议
    RT->>BR: ① Rekognition 快筛
    RT->>BR: ② Nova Pro 深度审核
    RT->>BR: ③ Guardrail 文本护栏
    RT->>CI: 执行 cn/eu/us.py (按 jurisdiction)
    CI-->>RT: 决策结果
    RT->>BR: ⑤ Sonnet 4.6 生成中文理由
    RT-->>API: report (decision + reason + 法规依据)
    API-->>CF: JSON
    CF-->>U: render
    Note over U,MEM: 用户标记误判 → API → MEM 写记忆<br/>下次相似图自动调阈值
```

## 关键设计决策

| 决策 | 取舍 |
|---|---|
| **CloudFront 单分发双源** | 一个域名同时服务前端和 API → 前端不用 CORS、cookie 不跨站。代价：失效缓存要走 `/api/*` 单独行为。 |
| **ALB internet-facing（不上 ACM）** | CloudFront → ALB 走 HTTP（VPC 出口仍是公网）。Demo 简化，省证书和 DNS。生产应改 internal ALB + VPC Origin。 |
| **Fargate arm64 单 task** | 与 `.bedrock_agentcore.yaml` 对齐；Demo 并发 ≤5，单 task 1vCPU/2GB 足够。 |
| **视频走 BackgroundTasks 而非 SQS** | 现有 `pipeline_video.py` 进度字典在内存，单进程 + 单 task = 进度查询能命中。生产换 SQS+DynamoDB。 |
| **UGC 与 Site bucket 分离** | UGC bucket 7 天过期 + presigned 直传；Site bucket 给 CloudFront OAC，私有。 |
| **配置走 SSM 而非环境变量** | `MEMORY_ID/GUARDRAIL_ID/CODE_INTERPRETER_ID/AGENT_RUNTIME_ARN` 由初始化脚本生成 → 写 SSM → ECS task 启动注入。换 ID 不用重建镜像。 |
| **AgentCore Runtime 已存在不重建** | `.bedrock_agentcore.yaml` 里 `agent_arn` 直接复用，CDK 不接管。CDK 只管前后端基础设施。 |
| **CLIENT_MODE=remote** | Fargate 后端调远程 AgentCore Runtime（microVM 隔离）。本地开发还是 `local`，与生产隔离。 |

## 成本（us-east-1，Demo 7×24）

| 资源 | 月成本 |
|---|---|
| Fargate 1 task (1vCPU / 2GB / arm64) | ~$30 |
| ALB (internet-facing) | ~$18 |
| NAT Gateway × 1 | ~$33 |
| CloudFront + S3 静态 | <$2 |
| S3 (UGC + Site) | <$2 |
| ECR (1 image) | <$1 |
| **基础设施小计** | **~$85/月** |
| **AgentCore + Bedrock 调用** | 按用量另算（最大头） |

> 演示前 1 小时启停模式：把 desired_count 调到 0，跌到 ~$50（剩 ALB + NAT）。

## 不在本架构里的（生产再加）

- WAF、Cognito 认证、API Key
- SQS + DynamoDB（异步任务）
- 多租户隔离（命名空间已有，但没有 quota / 限流）
- 多 AZ NAT（成本翻倍）
- 蓝绿发布、Canary
- X-Ray / OTel 全链路追踪
