# UGC 审核智能体 · v2 Hybrid · 运行机制全解

> 相比 [v1 Full-Agent](./architecture-v1-full-agent.md)：LLM 只出现在**真正需要推理的节点**。
>
> **基准预期**：低风险路径总耗时 **~10s**（v1 ~31.5s），高风险路径 **~25s**（v1 ~55s）。
>
> **AgentCore 组件使用不变**：Runtime / Memory / Code Interpreter / Gateway 一个不少，只是 Agent 数量从 6 降到 2。

---

## 0. 为什么做 v2

v1 把每个节点都实现成 Strands `Agent`——即便是"调一个 Rekognition API 把结果透传"这样的纯 I/O 步骤，也要 LLM 先"思考该不该调这个工具"、拿到结果再"思考输出 JSON"。这对固定漏斗流程是浪费。

实测 v1 一次审核耗时拆解：

| 类别 | 耗时 | 占比 |
|---|---|---|
| 工具调用（Rekognition + Nova + Code Interpreter + Memory） | ~16s | ~30% |
| **6 个 Agent 的 LLM ReAct 循环开销**（每个 2-3 轮 Bedrock InvokeModel） | **~37s** | **~70%** |

v2 的核心判断：**LLM 应该用在"综合上下文生成可解释裁决"这类真推理点，不该用在"决定调哪个 API"这类确定性编排点**。

---

## 1. 架构对比（v1 vs v2）

```
v1 Full-Agent (pipeline.py → Strands Graph)
  ┌─ orchestrator   Agent（Haiku）  ← 调 Memory + 挑阈值
  ├─ fast_screen    Agent（Haiku）  ← 调 2 个 Rekognition
  ├─ text_guard     Agent（Haiku）  ← 调 Guardrail
  ├─ deep_review    Agent（Haiku 外壳，调 Nova）
  ├─ decision_light Agent（Haiku）  ← 调 Code Interpreter
  └─ decision_heavy Agent（Sonnet） ← 调 Code Interpreter + 合成中文理由

v2 Hybrid (pipeline_hybrid.py → 纯 Python 编排)
  ┌─ [step 1] memory.recall      ← 纯代码调 API
  ├─ [step 2] rekognition ×2     ← 纯代码并行
  ├─ [step 3] text_guard         ← 纯代码调 API（有文字时）
  ├─ [step 4] deep_review Agent  🤖 Nova Pro（条件触发）
  └─ [step 5] 决策
       ├─ 低风险 → _decision_light() 纯代码调 Code Interpreter
       └─ 高风险 → decision_heavy Agent 🤖 Sonnet 4.6 合成裁决
```

**保留的 Agent（2 个）**：
1. **deep_review**：Nova Pro 本身就是多模态推理，需要 LLM 承上启下
2. **decision_heavy**：综合 Rekognition + Nova + Memory + 策略脚本，生成"给运营看"的中文理由

**被合并成确定性代码的节点（4 个）**：
1. orchestrator：`recall_similar_cases()` + 阈值调整 if/elif，没有 LLM 价值
2. fast_screen：两个 Rekognition API 并行调用，纯 I/O
3. text_guard：调 Guardrail 透传结果
4. decision_light：低风险路径只需要调 Code Interpreter 拿 PolicyResult，不需要 LLM 改写理由

---

## 2. v2 完整数据流

文件：`src/ugc_moderation/pipeline_hybrid.py`

```python
async def run_moderation_hybrid(content_s3_uri, jurisdiction, ...):
    case_id = f"case-{sid[:8]}"

    with build_session_manager(actor, sid, jurisdiction):   # AgentCore Memory 会话
        # Step 1 — 纯代码
        orch = _orchestrate(content_s3_uri, jurisdiction, actor)
        #   └─ recall_similar_cases (AgentCore Memory API)
        #   └─ if/elif 阈值调整 (75 → 65/85)

        # Step 2 — 纯代码，两个 Rekognition 并行
        fs = await _fast_screen(content_s3_uri)

        # Step 3 — 条件触发，纯代码
        tg = _text_guard(ocr_text) if (ocr_text or fs.has_text) else None

        # Step 4 — 真·Agent（条件触发）
        dr = None
        if _needs_deep_review(fs, orch.effective_threshold):
            dr = _run_deep_review_agent(content_s3_uri, jurisdiction, hint)
            # ↑ Strands Agent + BedrockModel(Haiku 4.5) + analyze_with_nova tool

        # Step 5 — 决策分流
        signals = _build_signals(fs, dr, tg, orch)
        if dr is None and (tg is None or tg.action == "NONE") and fs.max_confidence < threshold:
            # 低风险：纯代码调 Code Interpreter
            decision = _decision_light(jurisdiction, signals, orch)
        else:
            # 高/中风险：真·Agent 合成中文理由
            decision = _run_decision_heavy_agent(jurisdiction, signals, orch)

    return ModerationReport(...)
```

> `ModerationReport` schema 与 v1 完全一致，UI / AgentCore Runtime entrypoint / batch API 对两版都透明。

---

## 3. AgentCore 组件映射（完全不变）

| AgentCore 组件 | v1 调用方式 | v2 调用方式 | 是否变化 |
|---|---|---|---|
| **Runtime** | `@app.entrypoint` + Graph | `@app.entrypoint` + hybrid pipeline | 入口函数不变，只是内部实现换了 |
| **Memory** | orchestrator Agent tool call | step 1 直接调 `recall_similar_cases()` | 同一个 API，同一个 MEMORY_ID |
| **Code Interpreter** | decision_light/heavy Agent tool call | step 5 直接调（或 decision_heavy Agent 调） | 同一个 CI session，同一份 cn/eu/us.py |
| **Guardrails** | text_guard Agent tool call | step 3 直接调 | 同一个 GUARDRAIL_ID |
| **Bedrock Models** | 6 个 Agent 都要 LLM | 只有 deep_review + decision_heavy 要 | 少了 4 次 InvokeModel |
| **Gateway (MCP)** | 外部调 `@app.entrypoint` | 同上 | 无变化 |
| **Observability** | spans + events | 同上（span 名改成 `step:*`） | trace 视图完全兼容 |

**关键**：AgentCore Runtime 的"每会话独立 Firecracker microVM"是**容器级**隔离，与 Agent 数量**无关**。客户要的合规价值（microVM 隔离 + Memory 按 actorId 分区）在 v2 完全保留。

---

## 4. 两个保留 Agent 的职责

### 4.1 deep_review Agent 🤖
**模型**：Haiku 4.5（外壳） + Nova Pro（tool 内部）
**系统提示**：要求调用 `analyze_with_nova` 后直接返回 JSON
**为什么保留**：Nova Pro 的视觉理解 = 推理。让 Agent 承接 Nova 的输出并做轻量改写比纯代码更安全（比如 Nova 偶尔返回非 JSON 时 Agent 能重试）。
**触发条件**：`fs.max_confidence >= orch.effective_threshold` 或命中高风险 label 或边缘区间。

### 4.2 decision_heavy Agent 🤖
**模型**：Sonnet 4.6
**系统提示**：调 `run_jurisdiction_policy` 后合成完整中文理由（含内容概况、Nova 发现、命中规则、Memory 调整）
**为什么保留**：把 Rekognition label + Nova 中文理由 + Memory rationale + 策略脚本的 verdict 融合成**一段可以直接给运营看的话**——这是真正的推理工作，不是 if/else。
**触发条件**：有任一高风险信号（deep_review 命中 / Guardrail 触发 / max_confidence 越界）。

---

## 5. 时间预算（实测/预估）

### 5.1 低风险路径（无 deep_review、无 text_guard，走 decision_light）

```
t=0   pipeline 进入
t=0   ├─ build_session_manager                              [~3.0s] 首次 Memory 客户端
t=3   ├─ step 1: memory.recall                              [~1.5s]
t=4.5 ├─ step 2: rekognition ×2 (asyncio.gather)            [~1.8s] 并行
t=6.3 ├─ step 5: decision_light — Code Interpreter          [~3.5s]
t=9.8 └─ 返回 ModerationReport

总计 ~10s（v1 同路径 ~31.5s，-68%）
```

### 5.2 中/高风险路径（触发 deep_review + decision_heavy）

```
t=0    pipeline
t=0    ├─ build_session_manager                              [~3.0s]
t=3    ├─ step 1: memory.recall                              [~1.5s]
t=4.5  ├─ step 2: rekognition ×2                             [~1.8s]
t=6.3  ├─ step 3: text_guard (optional)                      [~0.8s]
t=7.1  ├─ step 4: deep_review Agent 🤖                        [~9.0s] Haiku 外壳 + Nova
t=16.1 ├─ step 5: decision_heavy Agent 🤖 Sonnet + CI         [~8.0s]
t=24.1 └─ 返回

总计 ~24s（v1 同路径 ~55s，-56%）
```

### 5.3 为什么 v2 还是 10s 而不是 3s

三个不可压缩的大块：
- AgentCore Memory 首次 client 创建（~3s 冷启动）
- Rekognition API 调用本身延迟（~1-2s/次）
- Code Interpreter session spin-up（~3-4s 首次）

这些是 AWS 服务本身的延迟，与 Agent 无关。想进一步优化需要：
- **Memory session 预热**：FastAPI `lifespan` 启动时预建 session
- **Code Interpreter session 复用**：长连接持有 session，跨请求复用
- **Rekognition 换内存图像调用**：避免 S3 `GetObject` 往返

---

## 6. 实现细节

### 6.1 @tool 解包
Strands 的 `@tool` 装饰器把函数包成 `DecoratedFunctionTool`。在 v2 我们通过 `.__wrapped__` 拿到原始 Python 函数直接调用，绕过 Strands 的 tool invocation 开销：

```python
from .tools.rekognition_tool import detect_moderation_labels
_detect_mod = detect_moderation_labels.__wrapped__

# v1 Agent 路径：LLM 生成 tool_use → Strands tool runtime 调 → 包结果
# v2 hybrid 路径：直接 _detect_mod(s3_uri) 就是普通函数调用
```

### 6.2 两个 Agent 的实例化
每次调用时内部新建 Agent 实例（`_run_deep_review_agent`、`_run_decision_heavy_agent`），保持和 v1 一样的 Strands Agent 代码，未来若要切回 Graph 编排也零成本。

### 6.3 结构化输出容错
两个 Agent 仍用"prompt 要求只输出 JSON" + Pydantic `model_validate` 校验。失败时：
- deep_review 失败 → 跳过 deep_review 字段（不阻塞决策）
- decision_heavy 失败 → fallback 到 `_run_policy()` 原始结果 + 兜底理由，保证永远有 DecisionOutput

---

## 7. 风险与权衡

| 风险 | v1 | v2 |
|---|---|---|
| 流程分支多样化需求 | ✅ Graph 拓扑天然支持 | ⚠️ 需要改 Python 代码 |
| 非标准工具调用需求（LLM 自己选工具） | ✅ Agent 自主决策 | ❌ 固定流程 |
| 延迟 | ❌ 58s | ✅ 10-25s |
| Bedrock InvokeModel 成本 | ❌ 12+ 次/审核 | ✅ 0-2 次/审核 |
| "智能体"叙事完整性 | ✅ 6 个 Agent | ⚠️ 只剩 2 个 Agent（但仍是 Agent 工程范本） |

> **演讲口径**：v2 不是"降级"，而是**最佳实践**——让 Agent 只出现在真正需要智能的地方。I/O 密集的确定性步骤交给 Python 编排是业界共识（参考 LangChain 新版推荐的 LCEL 模式、OpenAI Swarm、Anthropic 内部 Agent 实践）。

---

## 8. 切换方式

```bash
# v2（hybrid，推荐）
export PIPELINE_MODE=hybrid
uv run uvicorn backend.api:app --reload --port 8000

# v1（保留对比用）
export PIPELINE_MODE=agent      # 或不设置，默认就是 agent
uv run uvicorn backend.api:app --reload --port 8000
```

`/api/meta` 返回体里的 `pipeline_mode` 字段显示当前生效的引擎。AgentCore Runtime 部署时把 `PIPELINE_MODE` 加到环境变量里即可。

---

## 9. 延伸阅读

- [v1 架构文档（保留对比用）](./architecture-v1-full-agent.md)
- [两版对比一览表](./comparison.md)
- [客户方案文档](./solution.md)
- [部署 Runbook](./runbook.md)
