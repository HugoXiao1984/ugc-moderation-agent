# UGC Moderation Agent (Strands Agents × AgentCore)

一款面向 **UGC 平台** 与 **云存储合规场景** 的多模态内容审核智能体。不是"规则
引擎调 API"，而是由 Agent 自主编排审核漏斗、自适应法域策略、用记忆持续优化。

```
用户/系统上传 → AgentCore Runtime (microVM) →
    Orchestrator → ① Rekognition 快筛 → ② Nova Pro 深度审核
                 ↘ ③ Guardrail 文本护栏      ↗
                 → ④ 决策 Agent (Code Interpreter 执行 cn/eu/us.py)
    → AgentCore Memory (误判学习)
    → 输出：决策 + 中文理由 + 法规依据
```

## 核心卖点

| 能力 | 技术支撑 |
|---|---|
| **自适应法域策略** | AgentCore Code Interpreter 热执行 `cn/eu/us.py`，改规则不改 Agent 代码 |
| **四层漏斗自动编排** | Strands Graph + 条件边（显式决策路径，可视化、可解释） |
| **记忆驱动优化** | AgentCore Memory 记录误判反馈，Orchestrator 入口召回相似案例，动态调整阈值 |
| **模型分级 + 动态升降** | orchestrator/fast_screen/text_guard/deep_review/decision_light = **Haiku 4.5**（快+便宜），decision_heavy = **Sonnet 4.6**（中文理由深度推理）；按 `prior_risk` 自动分流。实测 48s → 31.5s (-35%) |
| **microVM 隔离** | AgentCore Runtime 每会话独立 Firecracker microVM，合规可审计 |

## 快速开始

### 1. 环境

```bash
# macOS 推荐
brew install uv
uv sync
cp .env.example .env
# 填入 AWS_REGION（默认 us-east-1）
```

### 2. 一次性创建 AWS 资源

```bash
uv run python scripts/create_memory.py            # → MEMORY_ID
uv run python scripts/create_guardrail.py         # → GUARDRAIL_ID
uv run python scripts/create_code_interpreter.py  # → CODE_INTERPRETER_ID (可选)
# 把上述 3 个 ID 贴进 .env
uv run python scripts/seed_memory.py              # 预塞 5 条误判样例
uv run python scripts/download_benchmark.py       # 拉取 Wikimedia 脱敏样本并上传到 DEMO_BUCKET
```

### 3. 本地跑 Demo（FastAPI 后端 + React 前端）

两个进程，需要分别启动：

```bash
# 终端 1: FastAPI 后端 (端口 8000)
uv sync --extra api
uv run uvicorn backend.api:app --reload --port 8000

# 终端 2: React 前端 (端口 5173)
cd ui
npm install
npm run dev
```

浏览器打开 <http://localhost:5173>。4 个 Tab：

1. **Single image** — 单图审核，实时流程图高亮，含"标记误判"按钮
2. **Jurisdictions** — 同图 CN/EU/US 三栏并排，差异高亮
3. **Memory loop** — 标记误判 → 再上传相似图 → 阈值自动调整
4. **Batch** — 并行多张 + 成本估算

### 4. 部署到 AgentCore Runtime（microVM 隔离）

```bash
uv pip install bedrock-agentcore-starter-toolkit
agentcore configure --entrypoint src/ugc_moderation/app.py
agentcore launch
agentcore invoke '{"content_s3_uri":"s3://demo/test.jpg","jurisdiction":"CN"}'
```

切到远程模式演示（后端调远程 AgentCore Runtime）：

```bash
export CLIENT_MODE=remote
export AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:...:agent-runtime/...
uv run uvicorn backend.api:app --reload --port 8000
# 前端无变化，继续 npm run dev
```

## 项目结构

```
src/ugc_moderation/
├── app.py                # AgentCore Runtime entrypoint
├── pipeline.py           # Graph 调用 + Report 组装
├── graph/                # 5-node Graph (state/conditions/build)
├── agents/               # orchestrator/fast_screen/deep_review/text_guard/decision
├── tools/                # @tool: Rekognition / Nova / Guardrail / Code Interpreter / Memory / S3
├── policies/             # Python-side mirror (load policies_scripts/*.py dynamically)
├── memory/               # AgentCore Memory session manager + namespaces
└── util/

policies_scripts/         # Code Interpreter 热执行的源文件
├── common.py
├── cn.py  # 中国 - 严格 + 红线
├── eu.py  # 欧盟 - DSA + GDPR 儿童
└── us.py  # 美国 - 宽松 + COPPA

backend/                  # FastAPI REST endpoints (单图/多法域/批量/上传/Memory/trace)
ui/                       # Vite + React + Tailwind 4 + shadcn-style dark dashboard
scripts/                  # 一次性初始化脚本
tests/                    # 单元测试 (24 passed)
docs/                     # 客户方案文档 / runbook
```

## 测试

```bash
uv run pytest -v
# 24 passed: 策略脚本差异化 + Graph 条件边 AND 语义 + _parse_last_json_blob
```

## 两个 Pipeline 版本（PIPELINE_MODE 切换）

本项目并存两套审核编排，方便演讲现场对比：

| 版本 | 入口 | Agent 数 | 低风险耗时 | 文档 |
|---|---|---|---|---|
| **v1 Full-Agent**（默认） | `src/ugc_moderation/pipeline.py` · Strands Graph | 6 | ~31.5s | [architecture-v1-full-agent.md](docs/architecture-v1-full-agent.md) |
| **v2 Hybrid**（推荐生产） | `src/ugc_moderation/pipeline_hybrid.py` · 纯 Python + 2 Agent | 2（deep_review + decision_heavy） | ~10s | [architecture-v2-hybrid.md](docs/architecture-v2-hybrid.md) |

切换方式：

```bash
export PIPELINE_MODE=hybrid   # 或 agent（默认）
uv run uvicorn backend.api:app --reload --port 8000
```

两版 Report schema、API、前端、AgentCore Runtime 入口完全一致。AgentCore（Memory / Code Interpreter / Runtime / Gateway）四大组件在两版中使用方式完全相同。

两版对比见 [docs/comparison.md](docs/comparison.md)。

## 下一步

见 `docs/solution.md` 客户方案文档、`docs/runbook.md` 部署排坑清单。
