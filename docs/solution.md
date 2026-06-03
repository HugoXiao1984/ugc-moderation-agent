# 多模态 UGC 内容审核智能体 · 客户方案

> Strands Agents × Amazon Bedrock AgentCore · 2026-05

## 1. 客户痛点

| 维度 | 传统规则引擎 | 本方案 |
|---|---|---|
| 策略更新 | 改代码、回归、发版 | **改 .py 脚本，Code Interpreter 热执行** |
| 法域差异 | 多套 if-else，难维护 | **cn/eu/us.py 分离，一行切换** |
| 误判处理 | 人工调阈值，全局覆盖 | **Memory 语义召回，按内容粒度自适应** |
| 可解释性 | label + confidence，不好给运营看 | **Nova Pro 生成中文理由 + 法规条款依据** |
| 模型选型 | 单模型通吃 / 硬编码 | **分级调度：Haiku 4.5 跑快筛层，Sonnet 4.6 只跑高风险推理；env 可覆盖** |
| 成本 | Nova 多模态 per 图 ~$0.012 | **快筛漏斗：约 10~30% 才升级到 Nova + Haiku 跑快筛层，单图 LLM 成本降 75%** |
| 合规隔离 | 同进程处理多租户 | **每会话独立 microVM，无污染** |

## 2. 架构总览

```
用户/系统上传 → S3
       ↓
AgentCore Gateway (MCP) ──→ AgentCore Runtime (Firecracker microVM)
                              │
                              ▼
                    ┌─────────────────────┐
                    │  Orchestrator Agent │  识别模态+法域+Memory 召回
                    └──┬──────────┬───────┘
                       │          │
        modality!=text │          │ text/mixed/OCR 有文字
                       ▼          ▼
           ┌────────────────┐  ┌──────────────┐
           │ 快筛 Rekognition│  │ 文本 Guardrail│
           └────┬───────────┘  └──────┬───────┘
                │ needs_deep_review   │
                ▼                     │
           ┌────────────┐             │
           │ Nova Pro   │             │
           │ 深度审核   │             │
           └────┬───────┘             │
                └──────┬──────────────┘
                       ▼
               ┌────────────────┐
               │ 决策 Agent     │  Code Interpreter → cn/eu/us.py
               │ + Memory 回写  │
               └────────────────┘
                       ↓
               决策 + 中文理由 + 法规依据
```

### 2.1 四层漏斗的动态编排

- **Orchestrator** 先读 Memory，召回相似历史误判，调整 `effective_threshold`（默认 75 → 65~85）
- **快筛 Agent** 跑 Rekognition。置信度低于阈值**且**未命中高风险标签 → 直接进决策
- **深度审核** 只在"边缘+高风险"时触发 → 80%~90% 的图不走 Nova，成本降一个数量级
- **文本护栏** 并行运行，不阻塞图像分支
- **决策 Agent** AND-gate 等齐必需前置，Code Interpreter 热执行法域脚本，返回"可直接给运营看的中文理由 + 法规条款"

### 2.2 四大卖点如何落地

| 卖点 | 代码位置 |
|---|---|
| 法域自适应 | `src/ugc_moderation/tools/code_interpreter_tool.py` 注入 `policies_scripts/{cn,eu,us}.py` |
| 记忆驱动 | `src/ugc_moderation/tools/memory_tool.py` + `agents/orchestrator.py` 召回逻辑 |
| 模型分级调度 | `src/ugc_moderation/settings.py::DEFAULT_AGENT_MODELS` + `graph/conditions.py::route_to_decision_{light,heavy}`（`prior_risk` 触发升档） |
| microVM 隔离 | `src/ugc_moderation/app.py` `@app.entrypoint` + AgentCore Runtime 部署 |

## 3. Demo 演讲流程（建议 8 分钟）

### Tab 1 · 单图审核（1.5 分钟）
"Agent 是怎么编排的？" — 上传健身举重图，展示右侧流程：Orchestrator → 快筛 → 决策（未升级到 Nova），报告里能看到中文理由和执行路径。

### Tab 2 · 法域对比（2 分钟）
"同一张图，不同法域什么结论？" — 同张图并行跑 CN/EU/US，三栏并排。例如一张 Suggestive=70% 的运动图：
- 🇨🇳 CN: **deny**（阈值 55）
- 🇪🇺 EU: **allow**（阈值 75）
- 🇺🇸 US: **allow**（阈值 90）

指出右下角的 `execution_mode: code_interpreter`：这些差异来自三份独立 .py 脚本，客户可以直接改文件改规则。

### Tab 3 · 记忆闭环（2 分钟）
"误判了怎么办？" — 把上个 Tab 里 CN 的 deny 结论标记为误判 → 切回 Tab 1 重新上传同类图 → 报告里"🧠 AgentCore Memory 调整记录"展开 → 阈值从 75 → 85。

这个演示最打动人：**Agent 自己学会了客户的业务偏好**。

### Tab 4 · 批量审核（1.5 分钟）
"规模怎么办？" — 拖 10 张图并行审核，表格显示每张的决策 + 是否升级深度审核。下方显示成本估算：10 张图里只有 3 张走了 Nova，比"全部走 Nova"便宜 70%。

### 现场切到 AWS Console（1 分钟）
打开 Bedrock AgentCore Runtime 面板，指向 "每个 session 一个 microVM"。打开 AgentCore Memory，查看 namespace `/misjudgments/demo-tenant/CN/` 下的记录（就是刚才 Demo 3 写入的）。

## 4. 成本估算（单次审核）

| 环节 | 单价（us-east-1，2026 Q1） | 触发频率 | 期望单次成本 |
|---|---|---|---|
| Rekognition DetectModerationLabels | $0.001/image | 100% | $0.001 |
| Rekognition DetectLabels | $0.001/image | 100% | $0.001 |
| Claude Haiku 4.5（5/6 Agent 快筛层） | ~$0.001/call × 3 轮 | 100% | $0.003 |
| Claude Sonnet 4.6（decision_heavy） | ~$0.008/call | ~30%（高风险才升档） | $0.002 |
| Nova Pro (image understanding) | ~$0.012/call | 20~30% (快筛过滤后) | $0.003 |
| Bedrock Guardrails | $0.75/1M chars | OCR/caption 有文字时 | <$0.001 |
| AgentCore Code Interpreter | 按 session 秒计费 | 每次审核 1 次 | <$0.001 |
| AgentCore Memory retrieve | 按请求计费 | 每次审核 1 次 | <$0.001 |
| **合计（期望）** | | | **~$0.011 / image** |

相比"所有图都走 Nova + Sonnet"（$0.022+），快筛漏斗 × 模型分级平均节省 50%。其中 **Haiku 4.5 跑快筛层** 把单次 LLM 成本从 Sonnet 的 ~$0.024 降到 ~$0.005（-80%），实测总耗时 48.5s → 31.5s（-35%）。

### 4.1 模型分级策略（可 env 覆盖）

| Agent | 默认模型 | env 变量 | 原因 |
|---|---|---|---|
| orchestrator / fast_screen / text_guard / deep_review / decision_light | Haiku 4.5 | `AGENT_MODEL_<NAME>` | 工具调用 + JSON 输出够用，快 2-3× 成本 1/10 |
| decision_heavy | Sonnet 4.6 | `AGENT_MODEL_DECISION_HEAVY` | 需综合推理 + 中文理由，保质量 |

客户可通过覆盖环境变量把 decision_heavy 换成自己的推理模型（比如切 Opus 4.7 跑极高风险内容）。

## 5. 落地路径

1. **POC (本方案)** — 单租户 FastAPI + React SPA（Vite + Tailwind 4 dark dashboard）+ 5~10 张测试图，本地直调或 AgentCore Runtime 远程模式二选一
2. **试点租户** — 对接客户 S3 事件，加 Cognito + ALB 鉴权，DynamoDB 人审队列
3. **多区域** — 部署到 ap-southeast-1（新加坡）服务 APAC；eu-west-1 服务 EU
4. **GA** — 接入客户真实法规库（如 Cyberwall API / LexisNexis）、多模态视频抽帧异步化、观测 Dashboard 生产化

## 6. 与传统方案对比

| 场景 | Rekognition 直调 | 自建 if-else 规则引擎 | **本方案** |
|---|---|---|---|
| 加一条新法规 | N/A | 改代码 + 回归 + 发版（1~2 周） | **改 .py + Memory seed（小时级）** |
| 误判多 | 只能调全局阈值 | 写特例 if | **语义召回按内容调阈值** |
| 审核理由 | 只有英文 label + conf | 模板拼接 | **Nova 生成中文理由 + 法规条款** |
| 法域切换 | 开多个账号 | 多套代码 | **一个参数** |
| 合规隔离 | 同进程 | 同进程 | **microVM 级** |

## 7. 可扩展方向

- **视频**：POC 已提供每秒抽帧 + 首违规短路版（`src/ugc_moderation/pipeline_video.py`），详见下一节
- **多租户**：AgentCore Memory actor_id = tenant_id，天然按租户隔离
- **人类反馈**：前端 "标记误判" 按钮（`POST /api/misjudgment`）可接入客户审核台账
- **生产可观测**：AgentCore Runtime 自动导出 OTel trace → CloudWatch ServiceLens 面板
- **MCP 网关**：客户已有 CMS 系统可通过 AgentCore Gateway 以 MCP 协议调用，无需改代码

---

## 8. 视频审核（POC 同步 + 生产异步）

### 8.1 POC 同步版（已实现，支持 live demo）

文件：`src/ugc_moderation/pipeline_video.py`

```
用户上传视频 (≤90s) → /api/upload → S3
       ↓
FastAPI /api/video/moderate  (同步一次调用，阻塞返回最终 verdict)
       ↓
① S3 GetObject 下载到 Runtime 临时目录
② ffmpeg 抽帧（1 帧 / 秒，JPEG 输出）
③ 逐帧上传回 S3 videoframes/{case_id}/sec_XXX.jpg
④ 分批并发（batch=5）走现有图像 hybrid pipeline
     └─ 首次命中高风险（label Confidence ≥ 90% 或 decision=deny）立即短路
⑤ 聚合 verdict + 标注命中时间戳（"第 7 秒命中 Explicit Nudity"）
```

**短路规则**：
- 任一帧 `decision == "deny"` → 视频整体 deny
- 任一帧 Rekognition 高风险 label（Explicit Nudity / Violence 等）置信度 ≥ 90% → 视频整体 deny
- 全部合规 → allow；部分 human_review 超过半数 → 整体 human_review

**演讲叙事**：
> "违规视频通常问题出现在早期——色情内容多在前几秒，暴力内容命中率高。我们分 5 帧一批并发审核，每批内部发现 deny 就停止——既保证速度，也保证成本可控。"

### 8.2 生产异步架构（架构图，不在 POC 代码里）

POC 的同步模式现场演讲体验最好（点按钮→看进度→出结果连贯），但生产不应该让前端 block 1 分钟等视频。生产部署建议：

```
用户上传视频 → S3 Multipart Upload
       ↓ (S3 Put Object event)
       ▼
┌──────────────────────────────────┐
│  S3 EventBridge Rule             │  按 bucket prefix + suffix 匹配
│  prefix: uploads/video/          │
│  suffix: .mp4 / .mov / .webm     │
└──────────┬───────────────────────┘
           ▼
┌──────────────────────────────────┐
│  Step Functions（可选）           │  编排长任务 + 重试策略
│   ├─ Lambda: 抽帧(ffmpeg layer)   │  并行抽帧→S3
│   └─ Map State: 并发帧审核         │  调 AgentCore Runtime
└──────────┬───────────────────────┘
           ▼
┌──────────────────────────────────┐
│  AgentCore Runtime (microVM)     │  本项目的图像 hybrid pipeline
│  /invoke payload = {frame_s3_uri}│  单帧 ~10-20s
└──────────┬───────────────────────┘
           ▼
┌──────────────────────────────────┐
│  DynamoDB: video_cases 表         │  状态 + 聚合 verdict
│  + SNS/WebSocket 通知前端         │
└──────────────────────────────────┘
```

**关键差异**：
- POC 前端 `await fetch("/api/video/moderate")` 阻塞等结果
- 生产前端上传完立刻 `POST /api/video/cases` 拿 `case_id` → WebSocket 订阅进度 → 每帧完成推一条 event → verdict 出来推最终 event
- POC 一个 request 跑满 1 分钟需要 HTTP keepalive；生产彻底解耦，Lambda/Runtime 挂了可重试

### 8.3 限制与取舍

| 维度 | POC 当前 | 生产建议 |
|---|---|---|
| 视频长度 | ≤90s（硬限） | 无硬限，分片处理 |
| 抽帧频率 | 1 帧/秒 | 按内容类型：静态 1 帧/2 秒、快剪辑 2 帧/秒 |
| 并发帧数 | batch=5（单机） | Step Functions Map state 无限水平扩展 |
| 触发方式 | 前端主动调 API | S3 EventBridge 异步 |
| 失败重试 | 无 | Step Functions 自动重试 + DLQ |
| 音频审核 | 未做 | 可加 AWS Transcribe → 再走文本 Guardrail |

---

**代码仓库**: `/Users/hugoxiao/ugc-moderation-agent/`
**运行指南**: 见 [README.md](../README.md)
**部署排坑**: 见 [runbook.md](./runbook.md)
