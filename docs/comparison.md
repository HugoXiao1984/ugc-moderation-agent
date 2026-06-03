# v1 Full-Agent vs v2 Hybrid · 方案对比

> 两版代码在同一仓库共存，通过 `PIPELINE_MODE` 环境变量切换。Report schema / API / 前端 / AgentCore 入口完全一致。

## 1. 一句话总结

- **v1**：每个节点都是 Strands `Agent`——最"纯"的 Agent 编排，演示 Strands Graph 能力上限
- **v2**：只在真正需要推理的节点（Nova Pro 深度审核、Sonnet 综合裁决）用 Agent，其他步骤是纯 Python 编排——面向生产的实用派

---

## 2. 关键指标对比

| 指标 | v1 Full-Agent | v2 Hybrid |
|---|---|---|
| Strands Agent 节点数 | **6** | **2**（deep_review + decision_heavy） |
| Bedrock InvokeModel 次数 / 审核 | ~12 次（6 Agent × 2 LLM 轮） | **0-2 次** |
| 低风险路径耗时 | ~31.5s | **~10s（-68%）** |
| 高风险路径耗时 | ~55s | **~24s（-56%）** |
| LLM 成本（单次审核） | ~$0.005 | **~$0.001**（低风险）/ ~$0.005（高风险） |
| Rekognition 调用 | 2 次 | 2 次 |
| Nova Pro 调用 | 条件触发 | 条件触发（相同条件） |
| Code Interpreter 调用 | 每次 1 次 | 每次 1 次 |
| AgentCore Memory 召回 | 每次 1 次 | 每次 1 次 |
| AgentCore Runtime microVM 隔离 | ✅ | ✅ |
| 策略热更（cn/eu/us.py） | ✅ | ✅ |
| 记忆驱动阈值调整 | ✅ | ✅ |

---

## 3. 节点级映射

| 职责 | v1 实现 | v2 实现 | v2 变化原因 |
|---|---|---|---|
| Memory 召回 + 阈值调整 | orchestrator Agent (Haiku) | `_orchestrate()` 纯函数 + `if/elif` | LLM 在这里不产生价值——规则是 4 条 if |
| Rekognition 快筛 | fast_screen Agent (Haiku) | `_fast_screen()` `asyncio.gather` | 纯 I/O，LLM 只是在透传 |
| 文本护栏 | text_guard Agent (Haiku) | `_text_guard()` 纯函数 | 同上 |
| Nova Pro 深度审核 | deep_review Agent 🤖 (Haiku + Nova tool) | **deep_review Agent 🤖 保留** | 视觉 + 中文理由生成是真推理 |
| 低风险决策 | decision_light Agent (Haiku + CI tool) | `_decision_light()` 纯函数 | PolicyResult 直接透传，无需 LLM 重写理由 |
| 高风险决策 | decision_heavy Agent 🤖 (Sonnet + CI tool) | **decision_heavy Agent 🤖 保留** | Rekognition + Nova + Memory + 策略结果的融合是真推理 |

---

## 4. 时间轴对比（同一张 sunset_lake.jpg @ CN 低风险）

### v1 (31.5s)
```
t=0     build_session_manager               [3.0s]
t=3.0   build_graph                         [0.5s]
t=3.6   graph.invoke_async                  [27.9s]
t=3.6     ├─ orchestrator Agent              [9.6s]   ← Haiku 2 轮
t=13.2    ├─ fast_screen Agent               [8.0s]   ← Haiku 2 轮
t=21.1    └─ decision_light Agent           [10.4s]   ← Haiku 2 轮 + CI
t=31.5   完成
```

### v2 (~10s)
```
t=0    build_session_manager                 [3.0s]
t=3.0  step 1: memory.recall                 [1.5s]
t=4.5  step 2: rekognition ×2 (并行)          [1.8s]
t=6.3  step 5: decision_light（纯代码+CI）    [3.5s]
t=9.8  完成
```

**净节省 21.7s**，主要来自：
- 省掉 6 次 Agent LLM 轮次（每次 ~3-5s）
- 省掉 Strands Graph 状态机开销（~0.5s/节点）

---

## 5. 成本对比（us-east-1，单次低风险审核）

| 项 | v1 | v2 |
|---|---|---|
| Rekognition (2 call) | $0.002 | $0.002 |
| AgentCore Memory retrieve | <$0.001 | <$0.001 |
| AgentCore Code Interpreter | <$0.001 | <$0.001 |
| Bedrock Haiku InvokeModel ×6 | ~$0.005 | **$0** |
| Bedrock Sonnet InvokeModel | $0 | $0 |
| Nova Pro | $0 | $0 |
| **合计** | **~$0.008** | **~$0.003（-60%）** |

高风险路径两版都触发 Nova + Sonnet，v2 仅省掉 orchestrator + fast_screen 的 2 次 Haiku，节省 ~$0.002。

---

## 6. "Agent 故事"怎么讲？

### v1 故事：**最大化 Agent 自主性**
> "这是 Strands Graph 的完整能力演示——每一步都由 Agent 自主决策调什么工具、怎么组合结果。AgentCore 每会话一个 microVM，12 次 LLM 调用全程可审计。"

适用场景：早期客户教育、展示 Strands + AgentCore 产品能力天花板。

### v2 故事：**Agent 工程最佳实践**
> "真正的 Agent 工程不是'哪里都塞 Agent'，是**让 LLM 只出现在需要智能的推理点**。v2 把 I/O 密集的确定性步骤还给 Python 编排，Agent 只负责两件事：视觉推理（Nova）和综合裁决（Sonnet）——延迟降 70%，成本降 60%，而 Agent 的价值反而更突出。"

适用场景：技术客户、生产落地讨论、与 Google Vertex / OpenAI Agents SDK 对标时。

### 三个核心卖点两版都在

| 卖点 | v1 | v2 |
|---|---|---|
| 法域自适应（Code Interpreter 热更 cn/eu/us.py） | ✅ | ✅ |
| 记忆驱动（AgentCore Memory 语义召回调阈值） | ✅ | ✅ |
| microVM 隔离（AgentCore Runtime 合规可审计） | ✅ | ✅ |

---

## 7. 如何现场对比演示

```bash
# 终端 1 (v1)
PIPELINE_MODE=agent  uv run uvicorn backend.api:app --port 8000

# 终端 2 (v2)
PIPELINE_MODE=hybrid uv run uvicorn backend.api:app --port 8001

# 前端指 8000 跑一遍，改环境变量 / 改 proxy 指 8001 再跑一遍
```

或用 `/api/meta` 字段 `pipeline_mode` 在前端 header 显示当前引擎 + 计时，直接观察差异。

---

## 8. 何时选 v1，何时选 v2

**选 v1 的理由**：
- 演示 Strands Graph + AgentCore 完整能力
- 流程分支未来有大量变化（希望 LLM 动态编排）
- 客户要看"最纯粹的 Agent 架构"

**选 v2 的理由**（生产推荐）：
- 延迟敏感（前端等待体验 / 大规模批量）
- 成本敏感（单次审核费用可预测）
- 流程已固定（四层漏斗不太会动）
- 面向工程落地，不追求"Agent 数量"炫技

---

## 9. 文档与代码索引

| 文档 | 内容 |
|---|---|
| [architecture-v1-full-agent.md](./architecture-v1-full-agent.md) | v1 完整说明 |
| [architecture-v2-hybrid.md](./architecture-v2-hybrid.md) | v2 完整说明 |
| [solution.md](./solution.md) | 客户方案（两版共用） |
| [runbook.md](./runbook.md) | 部署排坑（两版共用） |

| 代码 | 内容 |
|---|---|
| `src/ugc_moderation/pipeline.py` | v1 入口（Strands Graph） |
| `src/ugc_moderation/pipeline_hybrid.py` | v2 入口（Python 编排 + 2 Agent） |
| `src/ugc_moderation/graph/` | v1 专用 Graph 节点装配 |
| `src/ugc_moderation/agents/` | 两版共享的 Agent 工厂函数 |
| `src/ugc_moderation/tools/` | 两版共享的 @tool 函数 |
| `src/ugc_moderation/settings.py` | `PIPELINE_MODE` 开关位于 `Settings.pipeline_mode` |
