---
marp: true
theme: default
class: invert
paginate: true
size: 16:9
style: |
  section {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    padding: 60px 80px;
  }
  h1 { color: #7aa2f7; font-size: 40px; margin-bottom: 12px; }
  h2 { color: #9ece6a; font-size: 30px; margin-top: 0; border-bottom: 2px solid #3b4261; padding-bottom: 8px; }
  h3 { color: #e0af68; font-size: 22px; }
  code, pre { background: #1a1b26; color: #c0caf5; border-radius: 4px; font-size: 18px; }
  table { font-size: 20px; }
  th { background: #24283b; color: #7aa2f7; }
  td, th { padding: 8px 14px; border: 1px solid #3b4261; }
  blockquote { border-left: 4px solid #bb9af7; padding-left: 16px; color: #a9b1d6; font-style: italic; }
  .columns { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }
  .small { font-size: 18px; color: #a9b1d6; }
  .tag { display: inline-block; background: #3b4261; color: #7aa2f7; padding: 2px 10px; border-radius: 12px; font-size: 16px; margin-right: 6px; }
---

<!-- _class: invert lead -->

# Agentic Moderation
## 多模态 UGC 智能审核大脑

<br/>

**Strands Agents × Amazon Bedrock AgentCore**

<br/>

<span class="tag">图文</span> <span class="tag">短视频</span> <span class="tag">多法域</span> <span class="tag">可解释</span> <span class="tag">会学习</span>

---

## 为什么要做这件事

<div class="columns">

<div>

### 传统审核的痛点

- 规则引擎：改一条规则要改代码 + 回归 + 发版（1~2 周）
- 误判只能调全局阈值，伤及无辜
- 只给 label + confidence，运营看不懂、讲不清
- 多法域要多套代码，维护爆炸
- 同进程审核，合规审计难过

</div>

<div>

### 我们的破局点

- **Agent 自编排**：不是 if-else，是智能体根据上下文动态决策
- **大模型自解释**：为什么违规，生成可给运营看的中文理由
- **记忆自进化**：一次误判反馈，全网持续受益
- **法域热切换**：改 `.py` 即生效，无需重新部署
- **microVM 隔离**：每次审核独立安全沙箱

</div>

</div>

---

## 核心能力一览

| 能力 | 价值 |
|---|---|
| **四层自适应审核漏斗** | 90% 低风险内容在早期止步，成本降一个数量级 |
| **法域原生分治** | CN / EU / US 策略独立热更新，同图一键出差异化裁决 |
| **分级违规体系** | allow/deny/review 之上叠加 7 级 flag + 细粒度 tags，驱动运营分诊与 SLA |
| **短视频秒级短路** | 命中首个高风险帧即整段短路，大模型解读"是什么 + 为什么违规" |
| **记忆驱动自进化** | 运营一次标注，下次相似内容自动调阈 |
| **会话级合规隔离** | 每次审核独立 Firecracker microVM |

---

## Demo 1 · 单图智能审核

<div class="columns">

<div>

### 业务逻辑

1. 用户上传图片到 S3
2. Agent 根据**先验风险**选快/慢路径
3. Rekognition 快筛 → 低风险直接通过
4. 高风险升级 Nova Pro 深度理解
5. 大模型合成**中文审核理由** + **flag 分级** + **细粒度 tags**

</div>

<div>

### 展示亮点

- 右侧流程图实时高亮走过的节点
- 报告展示：
  - ✅ 决策（allow / deny / human_review）
  - 🏷️ flag 等级（999 / 998 / 997 / 200 / 100 / 1 / 2）
  - 🔖 业务 tags（色情/武器/未成年/吸烟 …）
  - 📝 2-4 句中文理由
  - 🧠 Memory 召回记录

</div>

</div>

---

## Demo 2 · 同图三法域对比

<div class="columns">

<div>

### 业务逻辑

同一张"健身举重"图，三个法域并行审核：

| 法域 | Suggestive 阈值 | 结论 |
|---|---|---|
| 🇨🇳 CN | 55 | **deny** |
| 🇪🇺 EU | 75 | **allow** |
| 🇺🇸 US | 90 | **allow** |

</div>

<div>

### 技术关键

- **共享上游信号**：Rekognition / Nova / TextGuard 只跑一次
- **只分叉决策层**：3 个法域并行调各自的 `.py` 策略脚本
- 结果：3 法域总耗时 ≈ 1 个法域的 1.1 倍
- 客户看到的就是**规则热更新** + **法域原生差异**

</div>

</div>

---

## Demo 3 · 记忆闭环

<div class="columns">

<div>

### 业务逻辑（3 步演示）

1. 上传一张边缘图 → 判 **deny**
2. 运营点「标记误判」→ 写入 AgentCore Memory
3. 再次上传相似图 → 报告显示：
   > 🧠 Memory 召回 1 条相似历史，阈值 75 → 85，本次 **allow**

</div>

<div>

### 客户看到的价值

> "Agent 自己学会了我们业务的偏好"

- 不是运营手动调全局阈值
- 而是**按内容语义粒度**自适应
- 一次标注 → 永久受益 → 全租户隔离

**这是 AI 从「执行工具」到「成长伙伴」的范式跃迁**

</div>

</div>

---

## Demo 4 · 批量审核

<div class="columns">

<div>

### 业务逻辑

- 拖 10 张图并行审核
- 表格实时显示每张的：
  - Decision 徽章
  - **Flag 分级**
  - Reasoning（中文理由摘要）
  - 是否升级深度审核
  - 置信度

</div>

<div>

### 成本可视化

- 10 张中只有 ~3 张升级 Nova Pro
- 对比"全部走 Nova"省约 **70%**
- 适用规模化场景：商品图审核、UGC 发布、直播截图

</div>

</div>

---

## Demo 5 · 短视频审核

<div class="columns">

<div>

### 业务逻辑

1. 用户上传短视频
2. 后端抽关键帧 → 批量并发送入图像管线
3. **命中首个高风险帧即整段短路**
4. 大模型对违规帧单独输出「画面内容 + 违规原因」
5. 聚合关键帧生成**视频主题摘要**

</div>

<div>

### 展示亮点

- 进度条 + 每阶段实时反馈
- 🎬 **视频理解**卡片：
  - 主题短语（如"户外徒步"）
  - 画面整体概述
  - 如有违规：明确解读违规时刻
- 🚫 **违规帧列表**：只列命中帧，不刷屏

</div>

</div>

---

## 技术架构

```
  用户上传 ──► S3 ──► AgentCore Gateway ──► AgentCore Runtime (microVM)
                                                      │
                                                      ▼
                                            ┌──────────────────┐
                                            │   Orchestrator   │  模态 + 法域 + Memory 召回
                                            └────┬─────────┬───┘
                                                 │         │ 有文字
                            modality != text     │         ▼
                                                 ▼    ┌─────────┐
                                          ┌──────────┐│  文本   │
                                          │ 快筛     ││ 护栏    │
                                          │Rekognition└────┬───┘
                                          └────┬─────┘     │
                                               │ 边缘/高风险 │
                                               ▼           │
                                          ┌──────────┐     │
                                          │ Nova Pro │     │
                                          │  深度    │     │
                                          └────┬─────┘     │
                                               └─────┬─────┘
                                                     ▼
                                            ┌──────────────┐
                                            │  决策 Agent  │ Code Interpreter → cn/eu/us.py
                                            │ + Memory 回写│  大模型输出 flag + tags
                                            └──────────────┘
```

---

## 技术核心 1：四层自适应漏斗

<div class="columns">

<div>

### 漏斗设计

- **Orchestrator**：先读 Memory，调整有效阈值
- **Rekognition**：100% 跑，秒级返回
- **Nova Pro**：只在边缘+高风险才触发（~20%）
- **文本护栏**：并行，不阻塞
- **决策 Agent**：AND-gate 汇合所有信号

</div>

<div>

### 为什么这么设计

- **延迟分层**：大多数图在第 1 层就止步
- **成本分层**：20% 的图跑最贵的模型
- **失败隔离**：某层超时/异常不拖垮整体
- **可观测**：每层都有独立 span / trace

**结果：平均单图成本下降约 50%+**

</div>

</div>

---

## 技术核心 2：法域热执行

<div class="columns">

<div>

### 文件布局

```
policies_scripts/
  ├── common.py   # PolicyResult dataclass
  ├── cn.py       # 中国：涉政红线 + 未成年保护
  ├── eu.py       # 欧盟：DSA 透明度 + GDPR
  └── us.py       # 美国：COPPA + 言论宽松
```

每个文件统一签名：
```python
def evaluate(signals: dict) -> PolicyResult:
    ...
```

</div>

<div>

### 执行机制

- **AgentCore Code Interpreter** microVM 热执行
- 每次把 `.py` 源码 + signals 注入沙盒
- 输出 JSON，Agent 解析后进入决策
- 改规则：**改 `.py` → 立即生效**
- 无需重新部署、无需回归测试

**客户价值：新法规上线从「1-2 周」缩短到「小时级」**

</div>

</div>

---

## 技术核心 3：分级违规体系

| flag | 含义 | decision | 示例 tags |
|---|---|---|---|
| **999** | 最严重违规 | deny | 色情 / 血腥暴力 / 引导广告 / 未成年涉风险 |
| **998** | 次严重 | deny | 武器 / 毒品 / 恐怖 / 冒犯宗教 |
| **997** | 文化冒犯 | human_review | 宗教敏感 / 种姓 / 政治 / 性话题 |
| **200** | 疑似未成年 | human_review | 15~18 岁 |
| **100** | 普通违规 | human_review | 吸烟 / 饮酒 / 诋毁 / 脏话 |
| **1** | 放行 | allow | 非色情性感动作 |
| **2** | 不可辨识 | allow | — |

**大模型在 JSON 输出中强制约束 flag 与 decision 一致**，并给 1~4 个业务 tags。

---

## 技术核心 4：短视频抽帧与短路

<div class="columns">

<div>

### 抽帧链路（AgentCore 原生）

```
视频 ──► S3
  │
  ▼ S3 GetObject
Code Interpreter microVM
  │ 1. pip install imageio-ffmpeg
  │ 2. ffmpeg -vf fps=1  抽帧
  │ 3. download_files 取回 JPEG
  ▼
上传所有帧到 S3
  │
  ▼ batch=5 并发
图像 hybrid pipeline
```

</div>

<div>

### 短路 + 解读

- **任一帧 decision=deny** → 整段 deny
- **任一帧 Rekognition 高风险 ≥ 90%** → 整段 deny
- 命中后：
  - 对违规帧**单独再跑一次 Nova**
  - 输出「画面内容：XXX。违规原因：XXX」
  - 聚合关键帧出**视频主题摘要**

**无需自建容器、无需 Lambda Layer，全在 AgentCore 生态内完成**

</div>

</div>

---

## 技术核心 5：记忆驱动自进化

<div class="columns">

<div>

### 误判反馈写入

运营点「标记误判」→ 存入 AgentCore Memory：

> "在 CN 法域下，一张「健身举重」图被快筛打上 Suggestive 78% 并 deny，
> 运营判定为误判（正确决策 allow）。
> 下次命中相似图时应将 Suggestive 阈值从 75 放宽到 85。"

</div>

<div>

### 召回与阈值自适应

下次审核时：
1. Orchestrator 读取 Memory，语义检索 top-3
2. 相关性 ≥ 0.75 才采用
3. 相似误判 → **阈值放宽**（75 → 85）
4. 相似漏判 → **阈值收紧**（75 → 65）
5. 调整理由写入报告，可审计

**Namespace 按 tenant × jurisdiction 隔离**

</div>

</div>

---

## 关键数据

<div class="columns">

<div>

### 延迟

| 路径 | 单次耗时 |
|---|---|
| 单图低风险（快筛通过）| ~10s |
| 单图高风险（Nova + Sonnet）| ~22s |
| 同图 3 法域（共享上游）| ~25s |
| 30s 视频（无违规）| ~1~2 min |
| 30s 视频（首帧违规短路）| ~15s |

</div>

<div>

### 成本（us-east-1 ）

| 项 | 单图 |
|---|---|
| Rekognition × 2 | $0.002 |
| Haiku 快筛层 × 3 | $0.003 |
| Sonnet 决策（30%）| $0.002 |
| Nova Pro（20~30%）| $0.003 |
| CI + Memory | <$0.001 |
| **合计（期望）** | **~$0.011 / 图** |

比「全走 Nova + Sonnet」省约 **50%**

</div>

</div>

---

## 落地路径

1. **POC（本方案）**
   - 单租户 FastAPI + React SPA
   - 5 个 Demo Tab 覆盖全链路
   - AgentCore Runtime 本地或远程二选一

2. **试点租户**
   - 对接客户 S3 事件
   - 加 Cognito + ALB 鉴权
   - DynamoDB 人审队列

3. **多区域 GA**
   - ap-southeast-1 服务 APAC
   - eu-west-1 服务 EU
   - 接入客户真实法规库
   - 接入 CloudWatch ServiceLens 观测面板

---

<!-- _class: invert lead -->

# 从「规则引擎」到「智能审核大脑」

<br/>

**Agent 自编排 · 大模型自解释 · 记忆自进化**

<br/>

不仅告诉运营**结果**，更解释**原因**；
不仅执行**策略**，更随业务**迭代**。

<br/>

<span class="small">Strands Agents × Amazon Bedrock AgentCore · 2026</span>
