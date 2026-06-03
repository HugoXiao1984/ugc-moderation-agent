# UGC 审核智能体 · 运行机制全解

> 供团队内部定位优化点。基于 2026-05-13 实测 trace。
>
> **当前基准（模型分级后）**：sunset_lake.jpg @ CN，本地模式，总耗时 **31.5 秒**（优化前 48.5s，-35%）
>
> 改动：orchestrator/fast_screen/text_guard/deep_review/decision_light → Haiku 4.5；decision_heavy 保留 Sonnet 4.6。Graph 新增 `decision_light` 节点（低风险快速路径）vs `decision_heavy`（完整推理路径），基于 orchestrator 输出的 `prior_risk` 分流。

## 0. 架构全景（6 层）

```
 ┌────────────────────────────────────────────────────────────────────┐
 │  入口层 │ React SPA → FastAPI │ AgentCore Runtime HTTP │ CLI/test  │   ← 不同触发方式
 ├────────────────────────────────────────────────────────────────────┤
 │  Pipeline 层 (src/ugc_moderation/pipeline.py)                      │   ← 统一编排
 │   run_moderation(content_s3_uri, jurisdiction, ...) → Report       │
 ├────────────────────────────────────────────────────────────────────┤
 │  Graph 编排层 (src/ugc_moderation/graph/)                           │   ← Strands Graph
 │   5 节点 + 6 条件边；AND-gate 决策汇合                              │
 ├────────────────────────────────────────────────────────────────────┤
 │  Agent 层 (src/ugc_moderation/agents/)                             │   ← LLM 驱动
 │   orchestrator / fast_screen / deep_review / text_guard / decision │
 ├────────────────────────────────────────────────────────────────────┤
 │  Tool 层 (src/ugc_moderation/tools/)                               │   ← AWS SDK 封装
 │   rekognition / nova / guardrail / code_interpreter / memory / s3  │
 ├────────────────────────────────────────────────────────────────────┤
 │  数据/资源层                                                        │   ← AWS 托管
 │   Rekognition · Bedrock (Claude+Nova+Guardrail) · AgentCore        │
 │   Memory / Code Interpreter · S3                                   │
 └────────────────────────────────────────────────────────────────────┘
```

---

## 1. 入口层：三个触发方式

| 入口 | 代码 | 调用路径 |
|---|---|---|
| **React SPA → FastAPI**（演讲/开发） | `ui/` (Vite + React + Tailwind 4 + 自建 shadcn 风组件) 打 `backend/api.py` 的 REST endpoints | 前端 `fetch("/api/moderate")` → FastAPI `@app.post` → 进程内 `pipeline.run_moderation()`；或由 FastAPI 切换到远程 `invoke_agent_runtime` |
| **AgentCore Runtime HTTP**（生产） | `src/ugc_moderation/app.py::invoke` `@app.entrypoint` | Firecracker microVM 里启动 HTTP server，收到 JSON payload → 调 `run_moderation()` |
| **CLI / 测试** | `pytest tests/`、`python scripts/*.py` | 直接调用纯函数 |

**远程/本地切换**：FastAPI 通过 `get_settings().client_mode` env 切换本地/远程：
- `local`：FastAPI endpoint 内 `await run_moderation(...)` — 进程内直跑
- `remote`：FastAPI endpoint 内 `boto3.client("bedrock-agentcore").invoke_agent_runtime(agentRuntimeArn=...)`

> **优化点 ①**：FastAPI 在 `local` 模式下每次 `/api/moderate` 请求都会重建 Graph（6 个 Agent + 一堆 Bedrock client）；用 `@lru_cache` 或 FastAPI `lifespan` 把 Graph 单例化，省每次 ~0.5s build 和客户端创建。

---

## 2. Pipeline 层：`run_moderation()` 做了什么

文件：`src/ugc_moderation/pipeline.py:40-113`

一次调用的完整数据流：

```python
async def run_moderation(content_s3_uri, jurisdiction, tenant_id, session_id, ocr_text):
    # ① 生成 case_id（span 追踪用）
    case_id = f"case-{sid[:8]}"; set_case(case_id)

    # ② 组装 task prompt (Orchestrator 的第一条 user message)
    task = build_moderation_task(content_s3_uri, jurisdiction, ocr_text)
    #   "请审核内容 s3://..., 声明法域 CN。请按系统提示调用工具并输出 JSON。"

    # ③ 打开 AgentCore Memory 会话（首次 ~2s 冷启动）
    with build_session_manager(actor, sid, jurisdiction) as _sm:

        # ④ 构造 Strands Graph（编排 6 个 Agent + 条件边）
        graph = build_moderation_graph()

        # ⑤ 执行 Graph（大头在这里，28s 左右）
        result = await graph.invoke_async(task, invocation_state={...})

        # ⑥ 从 result.results 提取每个节点的结构化输出（Pydantic 校验）
        orch = _extract(result.results, "orchestrator", OrchestratorOutput)
        fs = _extract(result.results, "fast_screen", FastScreenOutput)
        dr = _extract(result.results, "deep_review", DeepReviewOutput)   # 可能 None
        tg = _extract(result.results, "text_guard", TextGuardOutput)      # 可能 None
        # decision_heavy 优先（Sonnet），否则 decision_light（Haiku），恰好二选一
        decision = (_extract(..., "decision_heavy", DecisionOutput)
                    or _extract(..., "decision_light", DecisionOutput))

    # ⑦ 组装最终报告对象返回
    return ModerationReport(case_id, ..., decision, trace=[n.node_id for n in execution_order])
```

**关键依赖**：

- Memory session 通过 `build_session_manager` 上下文管理器包住整个 Graph 执行，session 内所有 Agent 的对话都会被记录到 AgentCore Memory 的 `/summaries/{actorId}/{sessionId}/` namespace（给未来的 long-term learning 用）。
- `_extract` 用 `_parse_last_json_blob`（条件边里也用）从 Agent 的自然语言输出里捞最后一段 JSON，再 Pydantic 校验。**Agent 的输出不是真正的结构化输出**，是在 prompt 里要求"只输出 JSON"。

> **优化点 ②**：Agent 输出用 **Strands `structured_output`** 接口直接绑 Pydantic schema，省掉一次"LLM 生成 JSON → 我们解析"的往返，每个节点至少省 3-5s。

---

## 3. Graph 编排层：Strands Graph 拓扑

文件：`src/ugc_moderation/graph/build.py:10-34`

```
                    ┌─────────────────────────┐
                    │    orchestrator         │  ← entry (Haiku 4.5)
                    │  识别模态+法域+Memory召回│
                    └──┬──────────────────┬───┘
    route_to_fast_screen│ (modality≠text)  │route_to_text_guard
                        ▼                  ▼
                 ┌─────────────┐     ┌──────────────┐
                 │ fast_screen │     │  text_guard  │
                 │ Rekognition │     │  Guardrail   │
                 │  (Haiku)    │     │  (Haiku)     │
                 └──┬──────────┘     └──────┬───────┘
  needs_deep_review │                       │
                    ▼                       │
              ┌──────────────┐              │
              │ deep_review  │              │
              │ Nova Pro tool│              │
              │  (Haiku外壳) │              │
              └──┬───────────┘              │
                 │                          │
         ┌───────┴──────────────────────────┤
         │    can_decide AND route_to_*     │
         │                                  │
route_to_decision_light                route_to_decision_heavy
(prior_risk=low + no signal)           (其他所有情况)
         ▼                                  ▼
 ┌──────────────────┐              ┌──────────────────┐
 │  decision_light  │              │  decision_heavy  │
 │  Haiku 4.5       │    二选一    │  Sonnet 4.6      │
 │  1-句话裁决      │─────OR──────▶│  详尽中文理由     │
 │  (Code Interp.)  │              │  (Code Interp.)  │
 └──────────────────┘              └──────────────────┘
                  ↓                         ↓
                       ModerationReport
```

### 条件边（`graph/conditions.py`）

Strands Graph 默认 **OR 语义**：任一入边触发就执行节点。我们用 AND-gate 解决"decision 必须等所有必需前置完成"，并用互斥 guard 分流到 light/heavy：

```python
# build.py
for upstream in ("fast_screen", "deep_review", "text_guard", "orchestrator"):
    builder.add_edge(upstream, "decision_light", condition=route_to_decision_light)
    builder.add_edge(upstream, "decision_heavy", condition=route_to_decision_heavy)
```

`route_to_decision_{light,heavy}` = `can_decide(state) AND/AND-NOT _is_low_risk(state)`。`_is_low_risk` 在 orchestrator 判定 prior_risk=low、fast_screen max_confidence=0、无文字、未升级 deep_review 时才返回 True。

`can_decide(state)` 内部算"根据 orchestrator 输出，这一次该等哪些节点"：

```python
# conditions.py:113-126
def _required_predecessors(state):
    required = ["orchestrator"]
    if modality != "text":                     # 非纯文本 → 必须走 fast_screen
        required.append("fast_screen")
    if fast_screen已完成 and needs_deep_review(state):  # 快筛升级
        required.append("deep_review")
    if route_to_text_guard(state):             # 含文字
        required.append("text_guard")
    return required

def can_decide(state):
    return 所有 required 节点都 COMPLETED
```

所以 `decision_{light,heavy}` 的入边会被触发多次（每次一个上游完成都 check 一次），但只有最后一个必需节点完成且 risk guard 满足时才真正触发 decision 节点执行——两个 decision 互斥，一次 invoke 恰好触发一个。

### 关键 Graph 源码（build.py）

```python
builder = GraphBuilder()
builder.add_node(build_orchestrator_agent(), "orchestrator")
builder.add_node(build_fast_screen_agent(), "fast_screen")
builder.add_node(build_deep_review_agent(), "deep_review")
builder.add_node(build_text_guard_agent(), "text_guard")
builder.add_node(build_decision_light_agent(), "decision_light")   # Haiku
builder.add_node(build_decision_heavy_agent(), "decision_heavy")   # Sonnet

builder.add_edge("orchestrator", "fast_screen", condition=route_to_fast_screen)
builder.add_edge("fast_screen", "deep_review", condition=needs_deep_review)

builder.add_edge("orchestrator", "text_guard", condition=route_to_text_guard)
builder.add_edge("fast_screen", "text_guard", condition=route_to_text_guard)
# 4×2 条入边到 decision_light / decision_heavy — 互斥 guard，一次恰好触发其一
for upstream in ("fast_screen", "deep_review", "text_guard", "orchestrator"):
    builder.add_edge(upstream, "decision_light", condition=route_to_decision_light)
    builder.add_edge(upstream, "decision_heavy", condition=route_to_decision_heavy)

builder.set_entry_point("orchestrator")
builder.set_execution_timeout(180)
```

> **优化点 ③**：你可以让 `text_guard` 和 `fast_screen` **真并行**——现在图面上是并行，但实际因为 text_guard 只在 `orchestrator.modality∈{text,mixed}` 或 `fast_screen.has_text` 时触发，而第二个条件需要 fast_screen 完成才知道。要真并行，得把"是否有文字"判断前移到 orchestrator（用 Rekognition DetectText 或轻量模型预判）。

> **优化点 ④**：如果 orchestrator 能直接确定是"纯 allow"场景（比如 phash 命中白名单），可以加一条 `orchestrator → decision_light` 的条件边短路 fast_screen，对无风险图再省 8s。

---

## 4. Agent 层：6 个 LLM Agent 各自干什么（模型分级后）

每个 Agent = **一个 Strands `Agent` 对象**（`strands.Agent(model, system_prompt, tools)`）。LLM 收到 task/context 后，按 system prompt 指令自主决定：(a) 调哪些 tool、(b) 调几次、(c) 最后输出什么 JSON。

**模型分级现状（`settings.DEFAULT_AGENT_MODELS`）**：

| Agent | Model | 理由 |
|---|---|---|
| orchestrator / fast_screen / text_guard / deep_review / decision_light | **Haiku 4.5** (`global.anthropic.claude-haiku-4-5-20251001-v1:0`) | 工具调用 + JSON 输出够用；速度 2-3× + 成本 1/10 |
| decision_heavy | **Sonnet 4.6** (`global.anthropic.claude-sonnet-4-6`) | 需综合推理 + 运营/法务可读中文理由，保质量 |

每个 Agent builder 支持 `model_id` 参数覆盖（见 `settings.model_for(agent_name)`），也可通过 `AGENT_MODEL_<NAME>` env var 运行时覆盖。

### 4.1 Orchestrator (`agents/orchestrator.py`)

**Model**: Haiku 4.5（可 env 覆盖）
**Tools**: `fetch_image_metadata`, `recall_similar_cases`
**职责**：
1. 拉 S3 元数据（size/content-type/phash）
2. 用自然语言描述内容 → 查 Memory 相似误判历史
3. 根据召回结果调整 `effective_threshold`（75 → 65~85）
4. 判断 modality（image/video/text/mixed）、prior_risk、是否需要 text_guard

**LLM 轮次**：2 轮（第一轮决定调 tool，第二轮看 tool 结果后生成 JSON）

**实测耗时**：15s（其中 LLM 思考 ~13.9s，tool 调用 ~1.2s）

### 4.2 FastScreen (`agents/fast_screen.py`)

**Model**: Claude Sonnet 4.6
**Tools**: `detect_moderation_labels`, `detect_labels`
**职责**：
1. 并行调两个 Rekognition API（Strands 的并行 tool call 机制）
2. 把标签列表 + max_confidence + has_text + has_person 结构化输出
3. 自判 `trigger_deep_review`（和条件边 `needs_deep_review` 形成双保险）

**LLM 轮次**：1 轮（一次 tool call 批量调 2 个，再一次 JSON 合成）

**实测耗时（Haiku 4.5）**：7.96s（LLM ~6.4s，2 个 Rekognition 并行 1.55s）· 对比 Sonnet 4.6 的 11.77s，-32%

### 4.3 DeepReview (`agents/deep_review.py`) — 可能跳过

**Model**: Haiku 4.5 外壳（真正的视觉理解由 tool 内部调 Nova Pro 完成）
**Tools**: `analyze_with_nova`
**职责**：把图交给 Nova Pro，拿回中文审核理由 + 风险标签 + OCR 文本

**触发条件**：`needs_deep_review(state)`，即 Rekognition 置信度 ≥ effective_threshold 或命中高风险标签

**预估耗时**：9-13s（Nova Pro 本身 5-9s + Haiku 外壳 ~4s）

### 4.4 TextGuard (`agents/text_guard.py`) — 可能跳过

**Model**: Haiku 4.5
**Tools**: `apply_guardrail`
**职责**：跑 Bedrock Guardrail 拿拦截结果

**触发条件**：`has_text_content(state)`

### 4.5 Decision Light / Heavy (`agents/decision.py`) — 二选一触发

两个 Agent 共享同一个 tool（`run_jurisdiction_policy`）和相似 schema，差异在 system_prompt 和 model：

**decision_light**（Haiku 4.5）
- system_prompt 要求 `reasoning_cn` 简短（1 句话）
- 触发：`route_to_decision_light` = `can_decide AND _is_low_risk`（prior_risk=low + fast_screen.max_confidence=0 + 无文字 + 未升级 deep_review）
- **实测耗时**：10.38s（LLM ~7.5s，CI 调用 2.83s）

**decision_heavy**（Sonnet 4.6）
- system_prompt 要求 `reasoning_cn` 详尽（2-4 句，含 Nova 描述 + 命中规则 + Memory 调整）
- 触发：`route_to_decision_heavy`（互斥 `NOT _is_low_risk`）
- **预估耗时**：15-19s（LLM ~12-16s，CI 调用 2.8s）

> **优化点 ⑤ ✅ 已实施**：原先全部用 Sonnet 4.6，现在 5/6 节点换 Haiku 4.5 + decision 分流 light/heavy。实测无风险图走 light 路径总耗时从 48.5s 降至 31.5s（-35%）。

---

## 5. Tool 层：7 个自定义 Tool 的实际工作

每个 tool 是 `@tool` 装饰的 Python 函数。Strands Agent 通过 tool use 协议调用（LLM 产出 tool_use block → runtime 执行 → tool_result 塞回上下文）。

| Tool | 文件 | 底层 AWS API | 实测耗时 |
|---|---|---|---|
| `detect_moderation_labels` | `tools/rekognition_tool.py:22` | `rekognition.detect_moderation_labels` | 1.5s |
| `detect_labels` | `tools/rekognition_tool.py:44` | `rekognition.detect_labels(Features=["GENERAL_LABELS"])` | 1.6s |
| `analyze_with_nova` | `tools/nova_vision_tool.py:43` | `bedrock-runtime.converse(modelId="us.amazon.nova-pro-v1:0")` | 5-9s |
| `apply_guardrail` | `tools/guardrail_tool.py:17` | `bedrock-runtime.apply_guardrail` | 0.5-1s |
| `run_jurisdiction_policy` | `tools/code_interpreter_tool.py:80` | AgentCore Code Interpreter `code_session.invoke("executeCode",...)` | 2.8s |
| `recall_similar_cases` | `tools/memory_tool.py:25` | AgentCore Memory `retrieve_memory_records` | 1.1s |
| `record_misjudgment` | `tools/memory_tool.py:65` | AgentCore Memory `create_event` | 0.3-0.6s |
| `fetch_image_metadata` | `tools/s3_tool.py:20` | `s3.get_object` + Pillow phash | 0.1s |

### `run_jurisdiction_policy` 特别说明（这是方案卖点）

文件：`src/ugc_moderation/tools/code_interpreter_tool.py:23-48,94-113`

```python
# 每次调用时实时拼 wrapper 脚本
wrapper = f"""
{common.py 源码}       # PolicyResult dataclass + helpers
{cn.py 源码}           # HIGH_RISK_LABELS_CN, RED_LINE_KEYWORDS, evaluate()
import json
_signals = json.loads('''...''')   # 快筛/Nova/护栏的结果
_result = evaluate(_signals)
print(json.dumps(_result.to_dict(), ensure_ascii=False))
"""

# 注入 AgentCore Code Interpreter 沙盒（Firecracker microVM 内 Python）
with code_session("us-east-1") as sess:
    resp = sess.invoke("executeCode", {"language": "python", "code": wrapper})
    stdout = _extract_stdout(resp)              # 从流式事件拼 stdout
    return json.loads(stdout.splitlines()[-1])  # 解析 PolicyResult JSON
```

**卖点**：客户要改阈值或新增法域，只需改 `policies_scripts/*.py` 文件，不用改 Agent 代码、不用重部署。下次调用会自动加载新版脚本。

**failure fallback**：如果 Code Interpreter session 失败，tool 自动用本地 `ugc_moderation.policies.evaluate` exec 同一份策略，返回里 `execution_mode=local_fallback` 标识。

> **优化点 ⑥**：Code Interpreter 每次 `code_session` 都会 `StartCodeInterpreterSession` 然后 `StopCodeInterpreterSession`（观察 CloudTrail），**2.8s 里 ~2s 是 session 生命周期开销**。可以在 pipeline 层维持一个 long-running session，每次 `invoke` 复用同一个 `sess`，把 2.8s 降到 ~0.8s。

---

## 6. 数据/资源层：AWS 资源映射

部署后实际存在的资源：

| 资源 | ID/ARN | 用途 |
|---|---|---|
| **Bedrock models** | `global.anthropic.claude-haiku-4-5-20251001-v1:0`（5/6 Agent LLM 快筛层）/ `global.anthropic.claude-sonnet-4-6`（decision_heavy 中文理由深度推理）/ `us.amazon.nova-pro-v1:0`（deep_review 视觉理解） | 模型推理 · 分级调度 |
| **Bedrock Guardrail** | `<GUARDRAIL_ID>` | 文本护栏（Hate/Sexual/Violence 等） |
| **Rekognition** | service-level | 快筛 label detection |
| **AgentCore Memory** | `<MEMORY_ID>`（3 策略：Semantic/UserPref/Summary） | 误判反馈语义召回 + session 历史 |
| **AgentCore Code Interpreter** | `<CODE_INTERPRETER_ID>` | 法域策略脚本热执行沙盒 |
| **AgentCore Runtime** | `<RUNTIME_NAME>` | 远程 microVM 托管运行时 |
| **S3 Demo bucket** | `ugc-moderation-demo-<ACCOUNT_ID>` | 待审内容 + 演讲测试图 |
| **S3 CodeBuild** | `bedrock-agentcore-codebuild-sources-<ACCOUNT_ID>-us-east-1` | deployment.zip 存放 |
| **Execution Role** | `AmazonBedrockAgentCoreSDKRuntime-us-east-1-<HASH>` | Runtime 的 IAM 身份 |

**跨资源的关键关系**：

- Agent LLM 输出 tool_use → runtime 调 `boto3.client("rekognition" 或 "bedrock-runtime" 或 "bedrock-agentcore")` → AWS 服务
- Orchestrator 调 `recall_similar_cases(summary, jurisdiction, actor_id)` → Memory 用 `retrieve_memory_records(memoryId, namespace="/misjudgments/demo-tenant", searchCriteria={searchQuery:..., topK:3})` 做语义相似召回
- Memory 里一条记录是自然语言描述（"在 CN 法域下健身房举重图被 deny 运营更正为 allow"），召回时按 cosine 相似度排序

---

## 7. 一次完整调用的时间轴（实测，模型分级后）

`sunset_lake.jpg` @ CN（走 decision_light 路径），总 **31.5 秒**：

```
t=0      pipeline 进入
t=0      ├─ build_session_manager (首次打 AgentCore Memory client) [3.0s]
t=3.0    ├─ build_moderation_graph (6 个 Agent 实例化)             [0.5s]
t=3.6    └─ graph.invoke_async 进入 (Strands Graph runtime)        [27.9s]
t=3.6      │
t=3.6      │  NODE: orchestrator (LLM=Haiku 4.5)                   [9.6s]
t=3.6      │   ├─ LLM 思考 + 产 tool_use                            ~2.1s
t=6.8      │   ├─ tool:memory.retrieve (AgentCore Memory)           [1.1s]
t=7.9      │   └─ LLM 合成 JSON                                     ~5.3s
t=13.2     │
t=13.2     │  [edge] route_to_fast_screen → True
t=13.2     │  NODE: fast_screen (LLM=Haiku 4.5)                    [8.0s]
t=13.2     │   ├─ LLM 思考 + 产 parallel tool_use                   ~2.9s
t=16.2     │   ├─ tool:detect_moderation_labels ┐并行               [1.5s]
t=16.2     │   ├─ tool:detect_labels            ┘                   [1.6s]
t=17.7     │   └─ LLM 合成 JSON                                     ~3.5s
t=21.1     │
t=21.1     │  [edge] needs_deep_review → False (max_conf=0)
t=21.1     │  [edge] has_text_content → False
t=21.1     │  [edge] _is_low_risk → True
t=21.1     │  [edge] route_to_decision_light → True (heavy 互斥)
t=21.1     │  NODE: decision_light (LLM=Haiku 4.5)                 [10.4s]
t=21.1     │   ├─ LLM 读 state + 产 tool_use                        ~4.8s
t=25.9     │   ├─ tool:run_jurisdiction_policy                      [2.4s]
t=25.9     │   │    ├─ StartCodeInterpreterSession                  ~1s
t=26.9     │   │    ├─ executeCode (cn.py)                          ~0.1s
t=27.0     │   │    └─ StopCodeInterpreterSession                   ~0.7s
t=28.3     │   └─ LLM 合成简洁 JSON                                  ~3.2s
t=31.5     │
t=31.5     pipeline 退出：ModerationReport (decision=allow)
```

### LLM vs Tool 耗时分布（Haiku 分级 + light 路径）

| 层 | 耗时 | 占比 |
|---|---|---|
| 工具 AWS API 调用（Rekognition/Memory/CI 合计） | ~6.6s | **21%** |
| Strands Agent LLM 推理（3 个节点 × Haiku 4.5） | ~21.4s | **68%** |
| Infra 启动（Memory session + Graph build） | ~3.5s | **11%** |

### 各路径预期耗时（分级后）

| 路径 | 触发条件 | 总耗时 |
|---|---|---|
| **light 路径（当前实测）** | prior_risk=low + 无风险信号 | **~31s** |
| heavy 路径（只换 decision 为 Sonnet） | 有风险信号但未升级 Nova | ~40s |
| full 路径（含 Nova + text_guard + heavy） | 边缘/混合模态 + 高风险 | ~55-65s |

---

## 8. 优化候选清单（按 ROI 排序）

| # | 优化 | 状态 | 预期收益（延迟） | 预期收益（成本） | 风险/工作量 |
|---|---|---|---|---|---|
| **1** | orchestrator/fast_screen/text_guard/deep_review 换 **Haiku 4.5** + decision 分 light/heavy | ✅ **已实施** | 实测 -17s (48.5→31.5) | -75% LLM 成本 | 零 |
| **2** | 用 Strands `structured_output` 绑 Pydantic，省 JSON 合成 LLM 回合 | 待做 | -3s × 3 节点 ≈ -9s | -30% | 中：每个 Agent 改 system_prompt + 换接口 |
| **3** | Code Interpreter session 长连接复用 | 待做 | -2s 每次 | 忽略 | 小：pipeline 加个模块级 session pool |
| **4** | `@lru_cache` / FastAPI `lifespan` 缓存 Graph + Bedrock clients | 待做 | -3.5s (仅本地模式) | 无 | 极小 |
| **5** | orchestrator 加 phash 白名单短路 `orchestrator → decision_light` 条件边 | 待做 | 无风险图 -17s | -40% (白名单流量) | 中：定义白名单管理、条件边 |
| **6** | Prompt caching（system prompt 长文本） | 待做 | -10% 到 -30% LLM 时间 | -30% LLM 成本 | 小：在 BedrockModel 开 cachePoint |
| **7** | Nova 深度审核流式返回，不等完整 JSON | 待做 | -3s (触发深度审核时) | 无 | 中：要改 nova_vision_tool 流式处理 |
| **8** | 把"是否有文字"判断前移到 orchestrator（调 Rekognition DetectText 一次） | 待做 | -8s (混合模态 text_guard 提前) | +1% | 中 |
| **9** | decision Agent 预写模板 + 填空 | 待做 | -3s | -20% | 中：但可能牺牲语言自然度 |
| **10** | 跳过 orchestrator 整个节点（让 fast_screen 直接作为 entry） | 待做 | -9s (多数场景) | -30% | 高：Memory 召回逻辑要搬去别处 |

**下一波最推荐 #3 + #4 + #5**：几乎零风险、一下午能搞定、预计把 31.5s 再压到 **~15s**（命中 phash 白名单时可达 ~7s）。

---

## 9. 两个你可能没注意的架构选择

### 9.1 为什么是 **Graph 而不是单 Agent + 多 Tool**？

单 Agent 让 LLM 自主决定调用顺序 → 更灵活但**决策路径不透明、无可视化、条件跳转靠 prompt 约束**。

Graph 让路径显式 → **客户演讲时能画出来**（四层漏斗图就是 Graph 拓扑）、**审计友好**（trace 里 trace 字段就是 `execution_order`）、**成本可控**（条件边严格控制 Nova 触发率）。

### 9.2 为什么策略脚本不是 Python 直接 import 而是 Code Interpreter？

如果 `from policies import cn, eu, us`，改规则就要重启/重部署 Agent。

Code Interpreter 方案里 `policies_scripts/*.py` 是**运行时加载**的文本（`Path(...).read_text()` 然后注入沙盒），客户改规则**不用重启**，甚至可以把策略存 S3/DynamoDB 动态拉取。这是方案文档的核心差异化点。**虽然慢 ~2s，但换来了策略热更 + 合规隔离两个卖点。**

---

## 相关文档

- `README.md` — 跑通步骤
- `docs/solution.md` — 客户方案 / 演讲脚本 / 成本模型
- `docs/runbook.md` — 首次部署排坑清单
- `scripts/show_trace.py` — 可视化单次调用 trace
