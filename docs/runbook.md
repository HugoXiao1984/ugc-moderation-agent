# 首次部署 Runbook

## 环境前置

- AWS 账户已在 **us-east-1** 启用以下服务：
  - Amazon Bedrock（申请 **Claude Haiku 4.5** + **Claude Sonnet 4.6** + **Nova Pro** 模型访问权）
  - Bedrock AgentCore（Runtime / Memory / Code Interpreter / Gateway GA）
  - Rekognition（默认开启，无需申请）
- IAM Principal (运行 uv/uvicorn/npm 的身份) 至少需要：
  - `bedrock:InvokeModel`, `bedrock:ApplyGuardrail`, `bedrock:CreateGuardrail`
  - `rekognition:DetectModerationLabels`, `rekognition:DetectLabels`
  - `bedrock-agentcore:*` (Runtime/Memory/Code Interpreter)
  - `bedrock-agentcore-control:*`
  - `s3:GetObject, PutObject` on `DEMO_BUCKET`
- 安装 `uv`（推荐）或 `pip + venv`；前端需要 `node >= 20` + `npm`
- （可选）`docker` / `finch` / `podman` 用于 `agentcore launch --local`

## 初始化顺序（必须按这个顺序做）

1. `uv sync` — 安装依赖
2. `cp .env.example .env` — 填入 `AWS_REGION=us-east-1`
3. `uv run python scripts/create_memory.py` — 输出 `MEMORY_ID`，贴回 .env
4. `uv run python scripts/create_guardrail.py` — 输出 `GUARDRAIL_ID`，贴回 .env
5. `uv run python scripts/create_code_interpreter.py` — 输出 `CODE_INTERPRETER_ID`（**可选**，不填会 fallback 到本地执行，依然能跑）
6. 创建 S3 Demo 桶：`aws s3 mb s3://ugc-moderation-demo --region us-east-1`（或自定义，改 `.env` 的 `DEMO_BUCKET`）
7. `uv run python scripts/seed_memory.py` — 预塞 5 条误判样例（Demo 3 效果立显）
8. `uv run python scripts/download_benchmark.py` — 拉 Wikimedia 样图

## 跑 Demo（本地模式，两个终端）

```bash
# 终端 1 — FastAPI 后端（默认监听 8000）
uv sync --extra api
uv run uvicorn backend.api:app --reload --port 8000

# 终端 2 — React SPA 前端（默认监听 5173，通过 vite proxy 转 /api 到 8000）
cd ui
npm install
npm run dev
```

浏览器访问 <http://localhost:5173>，4 个 Tab：Single / Jurisdictions / Memory loop / Batch。

## 部署到 AgentCore Runtime

```bash
uv pip install bedrock-agentcore-starter-toolkit
agentcore configure --entrypoint src/ugc_moderation/app.py
# 修改生成的 .bedrock_agentcore.yaml：
#   - 绑定 role_arn（要含第一节列出的权限）
#   - 把 MEMORY_ID / GUARDRAIL_ID / NOVA_MODEL_ID 放到 environment
agentcore launch
agentcore invoke '{"content_s3_uri":"s3://ugc-moderation-demo/demo/sunset_lake.jpg","jurisdiction":"CN"}'
```

切到远程模式（前端不变，FastAPI 改成调 AgentCore Runtime）：

```bash
# 终端 1 — 启动 FastAPI 走远程 AgentCore Runtime
export CLIENT_MODE=remote
export AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:...
uv run uvicorn backend.api:app --reload --port 8000

# 终端 2 — 前端无变化
cd ui && npm run dev
```

## 常见坑

### 1. Rekognition `InvalidS3ObjectException`
原因：Lambda/ACR 角色没有 `s3:GetObject` on the bucket，或者桶与 Rekognition 不同 region。
修复：确保 `DEMO_BUCKET` 和 `AWS_REGION` 同一区；给运行角色加 s3 只读。

### 2. Nova Pro `AccessDeniedException`
Bedrock 模型首次使用需要在控制台 "Model access" 里申请 Amazon Nova 家族访问权。申请通常秒级批。

### 3. `bedrock-agentcore` 包找不到
`bedrock-agentcore` 和 `bedrock-agentcore-starter-toolkit` 需要从 AWS 公共 PyPI 镜像拉取。
如果企业环境有代理，配置 `UV_INDEX_URL` / `PIP_INDEX_URL` 指向内部 mirror。

### 4. Code Interpreter 调用被限流 / 冷启动慢
第一次 `code_session` 大约 2~4s 冷启动。POC 里我们单次调用 session 自动释放，生产建议长连接复用。
如果 CI 不可用，tool 自动 fallback 到本地 exec —— 日志里会出现 `execution_mode=local_fallback`。

### 5. Memory retrieve 返回空
`MEMORY_ID` 正确，但 `actor_id` / namespace 对不上。本项目默认 `actor_id=demo-tenant`；确保 FastAPI、React SPA 传的 `tenant_id` 和 seed_memory 脚本都用同一个。

### 6. Strands Graph decision 节点提前触发
通常发生在条件边 OR 语义下。我们用 `can_decide` AND-gate 解决；如果仍看到 decision 先于 deep_review 完成，检查 `_required_predecessors` 是否正确反映所需节点。

### 7. FastAPI 上传图片返回 413 / 文件过大
`backend/api.py` 用 `python-multipart` 解析 multipart；默认没有写死上限，但反向代理（Nginx/ALB）可能拦截。
- 本地 `uvicorn` 无上限，通常直接能传到 ~50MB
- 前端 Uploader 组件本身不限制，但大图（>10MB）建议先客户端 resize
- 部署反代时显式放开 `client_max_body_size 50m;`（Nginx）或 ALB target group 的 `request body size`

### 8. 前端找不到后端 / CORS 报错
Vite dev server 默认通过 `ui/vite.config.ts` 的 proxy 把 `/api` 转到 `localhost:8000`。如果改了后端端口，同步改 `vite.config.ts`。
非本地部署（比如 FastAPI 单独上 ALB）需要把前端的 `/api` 改成绝对 URL，并在 `backend/api.py` 的 `CORSMiddleware` 里加上前端域名。

### 9. 模型分级：想让某个 Agent 用不同模型
所有 6 个 Agent 都支持 env 覆盖，格式 `AGENT_MODEL_<NAME>`：

```bash
# 例子：把 orchestrator 也升到 Sonnet（代价更高但更稳）
export AGENT_MODEL_ORCHESTRATOR=global.anthropic.claude-sonnet-4-6

# 例子：把 decision_heavy 换成 Opus 4.7
export AGENT_MODEL_DECISION_HEAVY=global.anthropic.claude-opus-4-7
```

默认值见 `src/ugc_moderation/settings.py::DEFAULT_AGENT_MODELS`。

## 卸载

```bash
agentcore destroy                           # 删 Runtime
aws bedrock delete-guardrail --guardrail-identifier $GUARDRAIL_ID
aws bedrock-agentcore-control delete-memory --memory-id $MEMORY_ID
aws bedrock-agentcore-control delete-code-interpreter --code-interpreter-id $CODE_INTERPRETER_ID
aws s3 rm s3://ugc-moderation-demo --recursive
aws s3 rb s3://ugc-moderation-demo
```
