// Generate UGC-Moderation-Demo.pptx from the content in docs/slides.md.
// Tokyo-Night-inspired dark theme. Run: `node scripts/gen_pptx.js`
//
// Palette (no '#' prefix per pptxgenjs rules):
//   BG_DARK   1a1b26  (primary background)
//   BG_PANEL  24283b  (card background)
//   BG_PANEL2 2f334d  (secondary card / hover)
//   BORDER    3b4261
//   TEXT      c0caf5  (body)
//   TEXT_DIM  a9b1d6
//   TEXT_MUTE 7982a9
//   ACC_BLUE  7aa2f7  (headings / links)
//   ACC_GRN   9ece6a  (section headers / success)
//   ACC_AMB   e0af68  (stats / flags)
//   ACC_MAG   bb9af7  (accent quotes)
//   ACC_RED   f7768e  (deny / warnings)

const pptxgen = require("pptxgenjs");

const C = {
  BG_DARK:   "1a1b26",
  BG_PANEL:  "24283b",
  BG_PANEL2: "2f334d",
  BORDER:    "3b4261",
  TEXT:      "c0caf5",
  TEXT_DIM:  "a9b1d6",
  TEXT_MUTE: "7982a9",
  ACC_BLUE:  "7aa2f7",
  ACC_GRN:   "9ece6a",
  ACC_AMB:   "e0af68",
  ACC_MAG:   "bb9af7",
  ACC_RED:   "f7768e",
};

const CJK = "PingFang SC";       // falls back on Windows to Microsoft YaHei
const MONO = "Menlo";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";      // 13.3" × 7.5" — more room for 中文
pres.title = "UGC Moderation Agent — Customer Demo";
pres.author = "Hugo";
const W = 13.333, H = 7.5;

// ------------------------------------------------------------------ helpers
function bg(slide) {
  slide.background = { color: C.BG_DARK };
}

function pageNum(slide, n, total) {
  slide.addText(`${n} / ${total}`, {
    x: W - 1.2, y: H - 0.45, w: 1.0, h: 0.3,
    fontSize: 10, fontFace: MONO, color: C.TEXT_MUTE, align: "right",
  });
}

function footer(slide) {
  slide.addText("Strands Agents × Amazon Bedrock AgentCore", {
    x: 0.5, y: H - 0.45, w: 8, h: 0.3,
    fontSize: 10, fontFace: CJK, color: C.TEXT_MUTE,
  });
}

function title(slide, text, subtitle) {
  slide.addText(text, {
    x: 0.6, y: 0.45, w: W - 1.2, h: 0.7,
    fontSize: 32, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.6, y: 1.1, w: W - 1.2, h: 0.4,
      fontSize: 14, fontFace: CJK, color: C.TEXT_DIM, margin: 0,
    });
  }
  // subtle divider
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.55, w: 1.2, h: 0.035,
    fill: { color: C.ACC_GRN }, line: { color: C.ACC_GRN, width: 0 },
  });
}

function card(slide, x, y, w, h, opts = {}) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: opts.fill || C.BG_PANEL },
    line: { color: opts.border || C.BORDER, width: 1 },
  });
}

function tag(slide, x, y, text, tone = "blue") {
  const fill = {
    blue: C.BG_PANEL2, green: "1e3a2d", amber: "3d2f15", red: "3d1f26", magenta: "2f1f3d",
  }[tone] || C.BG_PANEL2;
  const color = {
    blue: C.ACC_BLUE, green: C.ACC_GRN, amber: C.ACC_AMB, red: C.ACC_RED, magenta: C.ACC_MAG,
  }[tone] || C.ACC_BLUE;
  const w = Math.max(1.0, text.length * 0.18 + 0.3);
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h: 0.35, rectRadius: 0.08,
    fill: { color: fill }, line: { color, width: 0.5 },
  });
  slide.addText(text, {
    x, y, w, h: 0.35,
    fontSize: 10, fontFace: CJK, color, align: "center", valign: "middle", margin: 0,
  });
  return w;
}

// ------------------------------------------------------------------ slides

const TOTAL = 17;

// ─── Slide 1: Cover ───────────────────────────────────────────────
{
  const s = pres.addSlide();
  bg(s);

  // ambient gradient-ish: two translucent rectangles
  s.addShape(pres.shapes.OVAL, {
    x: -2, y: -2, w: 8, h: 8,
    fill: { color: C.ACC_BLUE, transparency: 85 }, line: { color: C.ACC_BLUE, width: 0, transparency: 100 },
  });
  s.addShape(pres.shapes.OVAL, {
    x: W - 5, y: H - 5, w: 9, h: 9,
    fill: { color: C.ACC_MAG, transparency: 90 }, line: { color: C.ACC_MAG, width: 0, transparency: 100 },
  });

  s.addText("Agentic Moderation", {
    x: 0.8, y: 1.9, w: W - 1.6, h: 1.0,
    fontSize: 56, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  s.addText("多模态 UGC 智能审核大脑", {
    x: 0.8, y: 2.95, w: W - 1.6, h: 0.8,
    fontSize: 32, fontFace: CJK, color: C.TEXT, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 3.85, w: 3.5, h: 0.04,
    fill: { color: C.ACC_GRN }, line: { color: C.ACC_GRN, width: 0 },
  });
  s.addText("Strands Agents × Amazon Bedrock AgentCore", {
    x: 0.8, y: 4.0, w: W - 1.6, h: 0.5,
    fontSize: 18, fontFace: CJK, color: C.TEXT_DIM, italic: true, margin: 0,
  });

  // tag row
  let tx = 0.8;
  ["图文审核", "短视频审核", "多法域自适应", "可解释", "会学习"].forEach((t, i) => {
    const tones = ["blue", "green", "amber", "magenta", "blue"];
    const w = tag(s, tx, 5.1, t, tones[i]);
    tx += w + 0.15;
  });

  s.addText("Hugo Xiao  ·  2026-05", {
    x: 0.8, y: H - 0.9, w: W - 1.6, h: 0.4,
    fontSize: 12, fontFace: MONO, color: C.TEXT_MUTE, margin: 0,
  });
}

// ─── Slide 2: 为什么要做这件事 ────────────────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "为什么要做这件事", "从「规则引擎」到「智能审核大脑」");

  // left card: 传统审核痛点
  card(s, 0.6, 2.1, 6.0, 4.8);
  s.addText("传统审核的痛点", {
    x: 0.85, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 20, fontFace: CJK, bold: true, color: C.ACC_RED, margin: 0,
  });
  s.addText([
    { text: "规则引擎：改一条规则要改代码 + 回归 + 发版（1-2 周）", options: { bullet: true, breakLine: true } },
    { text: "误判只能调全局阈值，伤及无辜", options: { bullet: true, breakLine: true } },
    { text: "只给 label + confidence，运营看不懂、讲不清", options: { bullet: true, breakLine: true } },
    { text: "多法域要多套代码，维护爆炸", options: { bullet: true, breakLine: true } },
    { text: "同进程审核，合规审计难过", options: { bullet: true } },
  ], {
    x: 0.85, y: 2.9, w: 5.5, h: 3.8,
    fontSize: 14, fontFace: CJK, color: C.TEXT_DIM,
    paraSpaceAfter: 10, margin: 0,
  });

  // right card: 我们的破局点
  card(s, 6.8, 2.1, 6.0, 4.8);
  s.addText("我们的破局点", {
    x: 7.05, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 20, fontFace: CJK, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText([
    { text: "Agent 自编排：智能体根据上下文动态决策", options: { bullet: true, breakLine: true } },
    { text: "大模型自解释：生成可给运营看的中文理由", options: { bullet: true, breakLine: true } },
    { text: "记忆自进化：一次误判反馈，全网持续受益", options: { bullet: true, breakLine: true } },
    { text: "法域热切换：改 .py 即生效，无需重部署", options: { bullet: true, breakLine: true } },
    { text: "microVM 隔离：每次审核独立安全沙箱", options: { bullet: true } },
  ], {
    x: 7.05, y: 2.9, w: 5.5, h: 3.8,
    fontSize: 14, fontFace: CJK, color: C.TEXT_DIM,
    paraSpaceAfter: 10, margin: 0,
  });

  footer(s); pageNum(s, 2, TOTAL);
}

// ─── Slide 3: 为什么选 Agentic（核心价值四象限）──────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "为什么选 Agentic", "不是把审核外包给 LLM，而是让系统具备三种智能");

  // 2×2 grid of advantages
  const advs = [
    {
      title: "① 运行时编排",
      sub: "不再写死 if-else",
      desc: "Orchestrator 根据模态、先验风险、Memory 召回实时决定走哪条路径；新增信号源只需加一个 @tool，无需改编排代码。",
      color: C.ACC_BLUE,
    },
    {
      title: "② 可解释输出",
      sub: "从「数字」到「理由」",
      desc: "大模型产出中文理由 + flag + tags，运营看得懂、客户可审计，满足 GDPR/DSA 透明度要求。",
      color: C.ACC_GRN,
    },
    {
      title: "③ 自然语言工具扩展",
      sub: "一小时接一个外部系统",
      desc: "客户内部 API → @tool + docstring，Agent 自动学会什么时候调。从「集成」到「赋能」。",
      color: C.ACC_AMB,
    },
    {
      title: "④ 会学习",
      sub: "AgentCore Memory",
      desc: "一次误判反馈 → 语义召回 → 下次相似内容自动调阈值，按内容粒度自适应，不是全局伤及无辜。",
      color: C.ACC_MAG,
    },
  ];

  const cardW = 6.05, cardH = 2.25;
  const startX = 0.6, startY = 1.9, gapX = 0.1, gapY = 0.15;
  advs.forEach((a, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = startX + col * (cardW + gapX);
    const y = startY + row * (cardH + gapY);
    card(s, x, y, cardW, cardH);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.08, h: cardH, fill: { color: a.color }, line: { color: a.color, width: 0 },
    });
    s.addText(a.title, {
      x: x + 0.3, y: y + 0.2, w: cardW - 0.5, h: 0.45,
      fontSize: 18, fontFace: CJK, bold: true, color: a.color, margin: 0,
    });
    s.addText(a.sub, {
      x: x + 0.3, y: y + 0.72, w: cardW - 0.5, h: 0.35,
      fontSize: 13, fontFace: CJK, italic: true, color: C.TEXT_DIM, margin: 0,
    });
    s.addText(a.desc, {
      x: x + 0.3, y: y + 1.15, w: cardW - 0.5, h: 1.0,
      fontSize: 12, fontFace: CJK, color: C.TEXT, margin: 0,
    });
  });

  // bottom tagline
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 6.55, w: 12.2, h: 0.5,
    fill: { color: C.BG_PANEL2 }, line: { color: C.ACC_MAG, width: 1 },
  });
  s.addText([
    { text: "传统规则引擎是", options: { color: C.TEXT_DIM } },
    { text: "「执行工具」", options: { color: C.ACC_AMB, bold: true } },
    { text: "，Agentic 系统是", options: { color: C.TEXT_DIM } },
    { text: "「会成长的审核助理」", options: { color: C.ACC_MAG, bold: true } },
    { text: "。", options: { color: C.TEXT_DIM } },
  ], {
    x: 0.6, y: 6.55, w: 12.2, h: 0.5,
    fontSize: 14, fontFace: CJK, italic: true, align: "center", valign: "middle", margin: 0,
  });

  footer(s); pageNum(s, 3, TOTAL);
}

// ─── Slide 4: Agentic 的坑 & 我们如何规避 ─────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "Agentic 的坑 & 我们如何规避", "客户最担心的 5 个问题，我们都有工程级答案");

  const risks = [
    { risk: "延迟不可控",         solution: "四层漏斗 + 模型分级：Haiku 跑快筛 / Sonnet 只跑决策", stat: "~22s 均值", color: C.ACC_BLUE },
    { risk: "成本不可控",         solution: "80% 内容压根不走大模型，快筛直接放行",                stat: "$0.011 / 图", color: C.ACC_GRN },
    { risk: "LLM 输出不稳定",     solution: "Pydantic schema + fallback：无合法 JSON 回退策略脚本", stat: "100% 可解析", color: C.ACC_AMB },
    { risk: "幻觉风险",           solution: "关键裁决走确定性策略脚本，LLM 只负责合成理由",          stat: "规则确定性",   color: C.ACC_RED },
    { risk: "难调试 / 不可观测", solution: "每层独立 span/trace，前端实时可视化流程图",              stat: "全链路可见",   color: C.ACC_MAG },
  ];

  const rowH = 0.85;
  const startY = 2.0;
  risks.forEach((r, i) => {
    const y = startY + i * (rowH + 0.1);
    card(s, 0.6, y, 12.2, rowH);
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y, w: 0.08, h: rowH, fill: { color: r.color }, line: { color: r.color, width: 0 },
    });
    // risk label
    s.addText(r.risk, {
      x: 0.9, y, w: 2.7, h: rowH,
      fontSize: 15, fontFace: CJK, bold: true, color: r.color, valign: "middle", margin: 0,
    });
    // solution
    s.addText(r.solution, {
      x: 3.7, y, w: 7.3, h: rowH,
      fontSize: 13, fontFace: CJK, color: C.TEXT, valign: "middle", margin: 0,
    });
    // stat
    s.addText(r.stat, {
      x: 11.05, y, w: 1.7, h: rowH,
      fontSize: 13, fontFace: MONO, bold: true, color: r.color,
      valign: "middle", align: "right", margin: 0,
    });
  });

  // bottom insight
  s.addText("核心原则：让大模型做它擅长的（推理、解释、判断边界），让确定性代码做它擅长的（执行、一致、可审计）。", {
    x: 0.6, y: 6.85, w: 12.2, h: 0.45,
    fontSize: 13, fontFace: CJK, italic: true, color: C.TEXT_DIM, align: "center", margin: 0,
  });

  footer(s); pageNum(s, 4, TOTAL);
}

// ─── Slide 5: 核心能力一览 ─────────────────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "核心能力一览", "六大维度重定义 UGC 审核");

  const caps = [
    { t: "四层自适应审核漏斗",  d: "90% 低风险内容在早期止步，成本降一个数量级", color: C.ACC_BLUE },
    { t: "法域原生分治",         d: "CN / EU / US 策略独立热更新，同图一键出差异化裁决", color: C.ACC_GRN },
    { t: "分级违规体系",         d: "allow/deny/review 之上叠加 7 级 flag + 细粒度 tags", color: C.ACC_AMB },
    { t: "短视频秒级短路",       d: "命中首个高风险帧即整段短路，大模型解读是什么+为什么", color: C.ACC_RED },
    { t: "记忆驱动自进化",       d: "运营一次标注，下次相似内容自动调阈", color: C.ACC_MAG },
    { t: "会话级合规隔离",       d: "每次审核独立 Firecracker microVM", color: C.ACC_BLUE },
  ];

  // 2 cols × 3 rows
  const cardW = 6.05, cardH = 1.5;
  const startX = 0.6, startY = 2.0, gapX = 0.1, gapY = 0.15;
  caps.forEach((c, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = startX + col * (cardW + gapX);
    const y = startY + row * (cardH + gapY);
    card(s, x, y, cardW, cardH);
    // accent bar
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.08, h: cardH, fill: { color: c.color }, line: { color: c.color, width: 0 },
    });
    s.addText(c.t, {
      x: x + 0.28, y: y + 0.15, w: cardW - 0.4, h: 0.45,
      fontSize: 17, fontFace: CJK, bold: true, color: c.color, margin: 0,
    });
    s.addText(c.d, {
      x: x + 0.28, y: y + 0.65, w: cardW - 0.4, h: 0.75,
      fontSize: 12, fontFace: CJK, color: C.TEXT_DIM, margin: 0,
    });
  });

  footer(s); pageNum(s, 5, TOTAL);
}

// ─── Slide 4: Demo 1 单图智能审核 ─────────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "Demo 1 · 单图智能审核", "Agent 自编排 + 大模型自解释");

  // left: 业务逻辑
  card(s, 0.6, 2.1, 6.0, 4.8);
  s.addText("业务逻辑", {
    x: 0.85, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  const steps = [
    "用户上传图片到 S3",
    "Agent 根据先验风险选快/慢路径",
    "Rekognition 快筛 → 低风险直接通过",
    "高风险升级 Nova Pro 深度理解",
    "大模型合成中文理由 + flag + tags",
  ];
  steps.forEach((st, i) => {
    const y = 2.9 + i * 0.7;
    // numbered bullet
    s.addShape(pres.shapes.OVAL, {
      x: 0.9, y: y + 0.05, w: 0.35, h: 0.35,
      fill: { color: C.ACC_BLUE }, line: { color: C.ACC_BLUE, width: 0 },
    });
    s.addText(String(i + 1), {
      x: 0.9, y: y + 0.05, w: 0.35, h: 0.35,
      fontSize: 13, fontFace: MONO, bold: true, color: C.BG_DARK,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(st, {
      x: 1.4, y: y, w: 5.0, h: 0.5,
      fontSize: 14, fontFace: CJK, color: C.TEXT, valign: "middle", margin: 0,
    });
  });

  // right: 展示亮点
  card(s, 6.8, 2.1, 6.0, 4.8);
  s.addText("展示亮点", {
    x: 7.05, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText([
    { text: "✓ 右侧流程图实时高亮走过节点", options: { breakLine: true, color: C.ACC_GRN } },
    { text: "", options: { breakLine: true, fontSize: 4 } },
    { text: "报告内容：", options: { breakLine: true, bold: true, color: C.TEXT } },
    { text: "• 决策（allow / deny / human_review）", options: { breakLine: true } },
    { text: "• flag 等级（999 / 998 / 997 / 200 / 100 / 1 / 2）", options: { breakLine: true } },
    { text: "• 业务 tags（色情 / 武器 / 未成年 / 吸烟 …）", options: { breakLine: true } },
    { text: "• 2-4 句中文理由（Sonnet 合成）", options: { breakLine: true } },
    { text: "• Memory 召回记录（阈值调整依据）", options: {} },
  ], {
    x: 7.05, y: 2.9, w: 5.5, h: 3.8,
    fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, paraSpaceAfter: 4, margin: 0,
  });

  footer(s); pageNum(s, 6, TOTAL);
}

// ─── Slide 5: Demo 2 法域对比 ──────────────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "Demo 2 · 同图三法域对比", "一张图，三个结论 — 差异来自代码，而非模型");

  // 3 verdict cards side by side
  const juris = [
    { flag: "🇨🇳", name: "CN", thr: 55, verdict: "DENY",  verdictColor: C.ACC_RED, desc: "涉政红线 + 未成年保护" },
    { flag: "🇪🇺", name: "EU", thr: 75, verdict: "ALLOW", verdictColor: C.ACC_GRN, desc: "DSA 透明度 + GDPR" },
    { flag: "🇺🇸", name: "US", thr: 90, verdict: "ALLOW", verdictColor: C.ACC_GRN, desc: "COPPA + 言论宽松" },
  ];
  juris.forEach((j, i) => {
    const x = 0.6 + i * 4.3, y = 2.1, w = 4.1, h = 3.0;
    card(s, x, y, w, h);
    s.addText(j.flag + "  " + j.name, {
      x: x + 0.3, y: y + 0.2, w: w - 0.6, h: 0.5,
      fontSize: 24, fontFace: CJK, bold: true, color: C.TEXT, margin: 0,
    });
    s.addText(`Suggestive 阈值: ${j.thr}`, {
      x: x + 0.3, y: y + 0.8, w: w - 0.6, h: 0.35,
      fontSize: 12, fontFace: MONO, color: C.TEXT_MUTE, margin: 0,
    });
    s.addText(j.verdict, {
      x: x + 0.3, y: y + 1.3, w: w - 0.6, h: 0.7,
      fontSize: 36, fontFace: MONO, bold: true, color: j.verdictColor, margin: 0,
    });
    s.addText(j.desc, {
      x: x + 0.3, y: y + 2.1, w: w - 0.6, h: 0.7,
      fontSize: 12, fontFace: CJK, color: C.TEXT_DIM, italic: true, margin: 0,
    });
  });

  // bottom: 技术关键
  card(s, 0.6, 5.3, 12.2, 1.6);
  s.addText("技术关键", {
    x: 0.85, y: 5.4, w: 11, h: 0.4,
    fontSize: 16, fontFace: CJK, bold: true, color: C.ACC_AMB, margin: 0,
  });
  s.addText([
    { text: "上游共享：", options: { bold: true, color: C.TEXT } },
    { text: "Rekognition / Nova / TextGuard 只跑一次", options: { breakLine: true } },
    { text: "分叉决策层：", options: { bold: true, color: C.TEXT } },
    { text: "3 个法域并行调各自的 .py 策略脚本", options: { breakLine: true } },
    { text: "结果：", options: { bold: true, color: C.TEXT } },
    { text: "3 法域总耗时 ≈ 1 法域的 1.1 倍", options: {} },
  ], {
    x: 0.85, y: 5.85, w: 12, h: 1.0,
    fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, paraSpaceAfter: 4, margin: 0,
  });

  footer(s); pageNum(s, 7, TOTAL);
}

// ─── Slide 6: Demo 3 记忆闭环 ──────────────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "Demo 3 · 记忆闭环", "一次误判反馈，下次自动改判 — 但硬红线永不松动");

  // timeline: 3 steps horizontal
  const steps = [
    { title: "1. 上传健身图",      desc: "Non-Explicit Nudity 96%\n按默认阈值判 deny", color: C.ACC_RED },
    { title: "2. 点「标记误判」", desc: "运营更正为 allow\n写入 AgentCore Memory", color: C.ACC_AMB },
    { title: "3. 再次上传相似图", desc: "语义召回历史误判 · 阈值 75 → 85\ndeny → allow 自动改判", color: C.ACC_GRN },
  ];
  steps.forEach((st, i) => {
    const x = 0.6 + i * 4.3, y = 2.1, w = 4.1, h = 2.3;
    card(s, x, y, w, h);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.08, h, fill: { color: st.color }, line: { color: st.color, width: 0 },
    });
    s.addText(st.title, {
      x: x + 0.28, y: y + 0.25, w: w - 0.5, h: 0.5,
      fontSize: 18, fontFace: CJK, bold: true, color: st.color, margin: 0,
    });
    s.addText(st.desc, {
      x: x + 0.28, y: y + 0.9, w: w - 0.5, h: 1.2,
      fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, margin: 0,
    });
    // arrow between cards
    if (i < 2) {
      s.addShape(pres.shapes.RIGHT_TRIANGLE, {
        x: x + w + 0.03, y: y + h / 2 - 0.18, w: 0.24, h: 0.36,
        fill: { color: C.BORDER }, line: { color: C.BORDER, width: 0 }, rotate: 90,
      });
    }
  });

  // bottom: two side-by-side cards — left=会学习, right=有底线
  // left: 记忆改判（会学习）
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 4.8, w: 6.05, h: 2.0,
    fill: { color: C.BG_PANEL2 }, line: { color: C.ACC_GRN, width: 2 },
  });
  s.addText("✓ 会学习：记忆驱动改判", {
    x: 0.85, y: 4.95, w: 5.6, h: 0.5,
    fontSize: 17, fontFace: CJK, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText([
    { text: "不是手动调全局阈值，而是", options: {} },
    { text: "按内容语义粒度自适应", options: { bold: true, color: C.TEXT } },
    { text: "。", options: { breakLine: true } },
    { text: "误判 → allow，漏判 → 转人审；", options: { breakLine: true } },
    { text: "一次标注 → 永久受益 → 全租户隔离。", options: {} },
  ], {
    x: 0.85, y: 5.5, w: 5.6, h: 1.2,
    fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, margin: 0,
  });

  // right: 硬红线保护（有底线）
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.75, y: 4.8, w: 6.05, h: 2.0,
    fill: { color: C.BG_PANEL2 }, line: { color: C.ACC_RED, width: 2 },
  });
  s.addText("✓ 有底线：硬红线永不松动", {
    x: 7.0, y: 4.95, w: 5.6, h: 0.5,
    fontSize: 17, fontFace: CJK, bold: true, color: C.ACC_RED, margin: 0,
  });
  s.addText([
    { text: "记忆只放宽", options: {} },
    { text: "边缘标签", options: { bold: true, color: C.TEXT } },
    { text: "（性暗示 / 非露骨 / 泳装）。", options: { breakLine: true } },
    { text: "色情 / 血腥 / 仇恨符号 / 涉政关键词", options: { bold: true, color: C.ACC_RED, breakLine: true } },
    { text: "命中即拒，记忆无权翻转 → 合规可审计。", options: {} },
  ], {
    x: 7.0, y: 5.5, w: 5.6, h: 1.2,
    fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, margin: 0,
  });

  footer(s); pageNum(s, 8, TOTAL);
}

// ─── Slide 7: Demo 4 批量审核 ──────────────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "Demo 4 · 批量审核", "规模化场景的成本可视化");

  // left: 业务逻辑
  card(s, 0.6, 2.1, 6.0, 4.8);
  s.addText("业务逻辑", {
    x: 0.85, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  s.addText([
    { text: "拖 10 张图，并行审核", options: { bullet: true, breakLine: true } },
    { text: "表格实时显示每张：", options: { bullet: true, breakLine: true } },
    { text: "Decision 徽章", options: { bullet: true, indentLevel: 1, breakLine: true } },
    { text: "Flag 分级 + Tags", options: { bullet: true, indentLevel: 1, breakLine: true } },
    { text: "中文理由摘要", options: { bullet: true, indentLevel: 1, breakLine: true } },
    { text: "是否升级深度审核", options: { bullet: true, indentLevel: 1, breakLine: true } },
    { text: "置信度", options: { bullet: true, indentLevel: 1 } },
  ], {
    x: 0.85, y: 2.9, w: 5.5, h: 3.8,
    fontSize: 14, fontFace: CJK, color: C.TEXT_DIM, paraSpaceAfter: 6, margin: 0,
  });

  // right: big stat
  card(s, 6.8, 2.1, 6.0, 4.8);
  s.addText("成本可视化", {
    x: 7.05, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText("-70%", {
    x: 7.05, y: 3.0, w: 5.5, h: 1.5,
    fontSize: 84, fontFace: MONO, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText("对比「全部走 Nova」的成本", {
    x: 7.05, y: 4.6, w: 5.5, h: 0.5,
    fontSize: 14, fontFace: CJK, color: C.TEXT_DIM, italic: true, margin: 0,
  });
  s.addText([
    { text: "10 张图中只有 ~3 张升级 Nova Pro", options: { breakLine: true } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "适用场景：", options: { bold: true, color: C.TEXT, breakLine: true } },
    { text: "• 商品图审核    • UGC 发布", options: { breakLine: true } },
    { text: "• 直播截图      • 社区头像", options: {} },
  ], {
    x: 7.05, y: 5.2, w: 5.5, h: 1.5,
    fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, margin: 0,
  });

  footer(s); pageNum(s, 9, TOTAL);
}

// ─── Slide 8: Demo 5 短视频审核 ────────────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "Demo 5 · 短视频审核", "命中即短路 + 大模型解读违规");

  // left: 业务逻辑
  card(s, 0.6, 2.1, 6.0, 4.8);
  s.addText("业务逻辑", {
    x: 0.85, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  const vsteps = [
    "用户上传短视频",
    "后端抽关键帧 → 批量并发入图像管线",
    "命中首个高风险帧即整段短路",
    "大模型对违规帧输出「画面+原因」",
    "聚合关键帧生成视频主题摘要",
  ];
  vsteps.forEach((st, i) => {
    const y = 2.9 + i * 0.7;
    s.addShape(pres.shapes.OVAL, {
      x: 0.9, y: y + 0.05, w: 0.35, h: 0.35,
      fill: { color: C.ACC_BLUE }, line: { color: C.ACC_BLUE, width: 0 },
    });
    s.addText(String(i + 1), {
      x: 0.9, y: y + 0.05, w: 0.35, h: 0.35,
      fontSize: 13, fontFace: MONO, bold: true, color: C.BG_DARK,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(st, {
      x: 1.4, y: y, w: 5.0, h: 0.5,
      fontSize: 14, fontFace: CJK, color: C.TEXT, valign: "middle", margin: 0,
    });
  });

  // right: 展示亮点 + 视频理解
  card(s, 6.8, 2.1, 6.0, 4.8);
  s.addText("展示亮点", {
    x: 7.05, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText([
    { text: "⏱", options: { color: C.ACC_BLUE } },
    { text: "  进度条 + 每阶段实时反馈", options: { breakLine: true, color: C.TEXT } },
    { text: "", options: { breakLine: true, fontSize: 4 } },
    { text: "🎬", options: { color: C.ACC_AMB } },
    { text: "  视频理解卡片", options: { breakLine: true, bold: true, color: C.TEXT } },
    { text: "• 主题短语（如「户外徒步」）", options: { breakLine: true } },
    { text: "• 画面整体概述", options: { breakLine: true } },
    { text: "• 如有违规：明确解读违规时刻", options: { breakLine: true } },
    { text: "", options: { breakLine: true, fontSize: 4 } },
    { text: "🚫", options: { color: C.ACC_RED } },
    { text: "  违规帧列表", options: { breakLine: true, bold: true, color: C.TEXT } },
    { text: "只列命中帧，不刷屏", options: { italic: true } },
  ], {
    x: 7.05, y: 2.9, w: 5.5, h: 3.8,
    fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, paraSpaceAfter: 4, margin: 0,
  });

  footer(s); pageNum(s, 10, TOTAL);
}

// ─── Slide 9: 技术架构 ──────────────────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "技术架构", "四层自适应漏斗 + AgentCore 原生");

  const nbox = (x, y, w, h, text, color, subText) => {
    card(s, x, y, w, h, { border: color });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.06, h, fill: { color }, line: { color, width: 0 },
    });
    s.addText(text, {
      x: x + 0.2, y: y + 0.08, w: w - 0.3, h: 0.38,
      fontSize: 13, fontFace: CJK, bold: true, color, margin: 0,
    });
    if (subText) {
      s.addText(subText, {
        x: x + 0.2, y: y + 0.46, w: w - 0.3, h: 0.3,
        fontSize: 10, fontFace: MONO, color: C.TEXT_MUTE, margin: 0,
      });
    }
  };
  // Horizontal arrow (rightward) — use flowLine with explicit arrowhead
  const hArrow = (x1, x2, y) => {
    s.addShape(pres.shapes.LINE, {
      x: x1, y, w: x2 - x1, h: 0,
      line: { color: C.TEXT_MUTE, width: 1.5, endArrowType: "triangle" },
    });
  };
  const vArrow = (x, y1, y2) => {
    s.addShape(pres.shapes.LINE, {
      x, y: y1, w: 0, h: y2 - y1,
      line: { color: C.TEXT_MUTE, width: 1.5, endArrowType: "triangle" },
    });
  };

  // Row 1 (top): S3 → Gateway → Runtime
  nbox(0.6, 2.0, 2.3, 0.78, "S3 上传", C.ACC_BLUE, "用户/系统");
  hArrow(2.95, 3.55, 2.39);
  nbox(3.6, 2.0, 2.5, 0.78, "AgentCore Gateway", C.ACC_BLUE, "MCP 协议");
  hArrow(6.15, 6.75, 2.39);
  nbox(6.8, 2.0, 2.8, 0.78, "AgentCore Runtime", C.ACC_BLUE, "Firecracker microVM");

  // Vertical arrow Runtime → Orchestrator
  vArrow(8.2, 2.82, 3.15);

  // Orchestrator (centered)
  nbox(4.5, 3.2, 4.3, 0.85, "Orchestrator", C.ACC_AMB, "模态 · 法域 · Memory 召回");

  // Three vertical arrows from Orchestrator to 3 branches
  vArrow(2.1, 4.1, 4.4);
  vArrow(6.65, 4.1, 4.4);
  vArrow(11.0, 4.1, 4.4);
  // horizontal connectors from Orch bottom to fanout top
  s.addShape(pres.shapes.LINE, {
    x: 2.1, y: 4.1, w: 9.0, h: 0,
    line: { color: C.TEXT_MUTE, width: 1.5 },
  });

  // Three branches
  nbox(0.6, 4.45, 3.0, 0.85, "快筛 Rekognition", C.ACC_GRN, "100% · 秒级返回");
  nbox(5.15, 4.45, 3.0, 0.85, "深度 Nova Pro",   C.ACC_MAG, "边缘+高风险 (~20%)");
  nbox(9.5, 4.45, 3.2, 0.85, "文本护栏 Guardrail", C.ACC_GRN, "并行不阻塞");

  // Three arrows converging to decision at y=5.75
  // Funnel: bring all three down to same horizontal line, then arrow down to decision
  const funnelY = 5.6;
  // vertical drops from each branch bottom (y=5.3) to funnel line
  s.addShape(pres.shapes.LINE, { x: 2.1, y: 5.3, w: 0, h: 0.3, line: { color: C.TEXT_MUTE, width: 1.5 } });
  s.addShape(pres.shapes.LINE, { x: 6.65, y: 5.3, w: 0, h: 0.3, line: { color: C.TEXT_MUTE, width: 1.5 } });
  s.addShape(pres.shapes.LINE, { x: 11.0, y: 5.3, w: 0, h: 0.3, line: { color: C.TEXT_MUTE, width: 1.5 } });
  // horizontal funnel
  s.addShape(pres.shapes.LINE, { x: 2.1, y: funnelY, w: 8.9, h: 0, line: { color: C.TEXT_MUTE, width: 1.5 } });
  // final arrow down to decision
  vArrow(6.65, funnelY, 5.9);

  // Decision
  nbox(4.2, 5.95, 4.9, 0.9, "决策 Agent", C.ACC_RED,
       "Code Interpreter → cn/eu/us.py · flag + tags");

  footer(s); pageNum(s, 11, TOTAL);
}

// ─── Slide 10: 技术核心 1 · 四层漏斗 ─────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "技术核心 1 · 四层自适应漏斗", "为什么低风险内容不跑 Nova");

  // left: 漏斗设计
  card(s, 0.6, 2.1, 6.0, 4.8);
  s.addText("漏斗设计", {
    x: 0.85, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  s.addText([
    { text: "Orchestrator：读 Memory 调整有效阈值", options: { bullet: true, breakLine: true } },
    { text: "Rekognition：100% 跑，秒级返回", options: { bullet: true, breakLine: true } },
    { text: "Nova Pro：只在边缘+高风险才触发（~20%）", options: { bullet: true, breakLine: true } },
    { text: "文本护栏：并行，不阻塞", options: { bullet: true, breakLine: true } },
    { text: "决策 Agent：AND-gate 汇合所有信号", options: { bullet: true } },
  ], {
    x: 0.85, y: 2.9, w: 5.5, h: 3.8,
    fontSize: 14, fontFace: CJK, color: C.TEXT_DIM, paraSpaceAfter: 10, margin: 0,
  });

  // right: 为什么这么设计
  card(s, 6.8, 2.1, 6.0, 4.8);
  s.addText("为什么这么设计", {
    x: 7.05, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText([
    { text: "延迟分层：", options: { bold: true, color: C.TEXT } },
    { text: "大多数图在第 1 层就止步", options: { breakLine: true } },
    { text: "成本分层：", options: { bold: true, color: C.TEXT } },
    { text: "只有 20% 的图跑最贵的模型", options: { breakLine: true } },
    { text: "失败隔离：", options: { bold: true, color: C.TEXT } },
    { text: "某层超时/异常不拖垮整体", options: { breakLine: true } },
    { text: "可观测：", options: { bold: true, color: C.TEXT } },
    { text: "每层独立 span / trace", options: { breakLine: true } },
    { text: "", options: { breakLine: true, fontSize: 4 } },
    { text: "结果：平均单图成本下降 50%+", options: { bold: true, color: C.ACC_AMB, italic: true } },
  ], {
    x: 7.05, y: 2.9, w: 5.5, h: 3.8,
    fontSize: 14, fontFace: CJK, color: C.TEXT_DIM, paraSpaceAfter: 6, margin: 0,
  });

  footer(s); pageNum(s, 12, TOTAL);
}

// ─── Slide 11: 技术核心 2 · 法域热执行 ─────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "技术核心 2 · 法域热执行", "改规则即生效，无需重新部署");

  // left: file layout
  card(s, 0.6, 2.1, 6.0, 4.8, { fill: C.BG_PANEL });
  s.addText("文件布局", {
    x: 0.85, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  s.addText([
    { text: "policies_scripts/",             options: { breakLine: true, color: C.ACC_AMB, bold: true } },
    { text: "  ├── common.py",                options: { breakLine: true, color: C.TEXT } },
    { text: "  │      # PolicyResult dataclass", options: { breakLine: true, color: C.TEXT_MUTE } },
    { text: "  ├── cn.py",                    options: { breakLine: true, color: C.TEXT } },
    { text: "  │      # 涉政红线 + 未成年保护", options: { breakLine: true, color: C.TEXT_MUTE } },
    { text: "  ├── eu.py",                    options: { breakLine: true, color: C.TEXT } },
    { text: "  │      # DSA 透明度 + GDPR",  options: { breakLine: true, color: C.TEXT_MUTE } },
    { text: "  └── us.py",                    options: { breakLine: true, color: C.TEXT } },
    { text: "         # COPPA + 言论宽松",    options: { color: C.TEXT_MUTE } },
  ], {
    x: 0.85, y: 2.9, w: 5.5, h: 2.3,
    fontSize: 12, fontFace: MONO, color: C.TEXT, paraSpaceAfter: 1, margin: 0,
  });
  s.addText([
    { text: "统一签名：", options: { breakLine: true, color: C.TEXT, bold: true } },
    { text: "def evaluate(signals: dict) -> PolicyResult", options: { color: C.ACC_GRN } },
  ], {
    x: 0.85, y: 5.4, w: 5.5, h: 1.3,
    fontSize: 12, fontFace: MONO, margin: 0,
  });

  // right: 执行机制
  card(s, 6.8, 2.1, 6.0, 4.8);
  s.addText("执行机制", {
    x: 7.05, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText([
    { text: "AgentCore Code Interpreter microVM 热执行", options: { bullet: true, breakLine: true } },
    { text: "每次把 .py 源码 + signals 注入沙盒", options: { bullet: true, breakLine: true } },
    { text: "输出 JSON，Agent 解析后进入决策", options: { bullet: true, breakLine: true } },
    { text: "改规则：改 .py → 立即生效", options: { bullet: true, breakLine: true } },
    { text: "无需重新部署、无需回归测试", options: { bullet: true } },
  ], {
    x: 7.05, y: 2.9, w: 5.5, h: 2.5,
    fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, paraSpaceAfter: 6, margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.05, y: 5.5, w: 5.5, h: 1.2,
    fill: { color: C.BG_PANEL2 }, line: { color: C.ACC_AMB, width: 2 },
  });
  s.addText("客户价值：新法规上线", {
    x: 7.2, y: 5.55, w: 5.3, h: 0.35,
    fontSize: 12, fontFace: CJK, color: C.TEXT_DIM, margin: 0,
  });
  s.addText("1-2 周  →  小时级", {
    x: 7.2, y: 5.9, w: 5.3, h: 0.7,
    fontSize: 24, fontFace: MONO, bold: true, color: C.ACC_AMB, margin: 0,
  });

  footer(s); pageNum(s, 13, TOTAL);
}

// ─── Slide 12: 技术核心 3 · 分级违规体系 ────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "技术核心 3 · 分级违规体系", "flag + tags 驱动运营分诊");

  // table-like layout using rows
  const rows = [
    { flag: "999", label: "最严重违规",   decision: "deny",         tags: "色情 / 血腥暴力 / 引导广告 / 未成年涉风险", color: C.ACC_RED },
    { flag: "998", label: "次严重",        decision: "deny",         tags: "武器 / 毒品 / 恐怖 / 冒犯宗教",             color: C.ACC_RED },
    { flag: "997", label: "文化冒犯",      decision: "human_review", tags: "宗教敏感 / 种姓 / 政治 / 性话题",           color: C.ACC_AMB },
    { flag: "200", label: "疑似未成年",    decision: "human_review", tags: "15-18 岁",                                  color: C.ACC_AMB },
    { flag: "100", label: "普通违规",      decision: "human_review", tags: "吸烟 / 饮酒 / 诋毁 / 脏话",                 color: C.ACC_AMB },
    { flag: "1",   label: "放行",          decision: "allow",        tags: "非色情性感动作",                            color: C.ACC_GRN },
    { flag: "2",   label: "不可辨识",      decision: "allow",        tags: "—",                                         color: C.ACC_GRN },
  ];
  // header
  const hx = 0.6, hy = 2.1, hw = 12.2, rowH = 0.55;
  s.addShape(pres.shapes.RECTANGLE, {
    x: hx, y: hy, w: hw, h: rowH,
    fill: { color: C.BG_PANEL2 }, line: { color: C.BORDER, width: 0 },
  });
  ["Flag", "含义", "Decision", "示例 Tags"].forEach((h, i) => {
    const xs = [0, 1.2, 3.8, 5.8].map(d => hx + d);
    s.addText(h, {
      x: xs[i], y: hy, w: [1.2, 2.6, 2.0, 6.4][i], h: rowH,
      fontSize: 13, fontFace: CJK, bold: true, color: C.ACC_BLUE,
      valign: "middle", margin: 0, align: i === 0 ? "center" : "left",
    });
  });
  rows.forEach((r, i) => {
    const y = hy + rowH + i * rowH;
    if (i % 2 === 0) {
      s.addShape(pres.shapes.RECTANGLE, {
        x: hx, y, w: hw, h: rowH,
        fill: { color: C.BG_PANEL }, line: { color: C.BORDER, width: 0 },
      });
    }
    s.addText(r.flag, {
      x: hx + 0.2, y, w: 0.9, h: rowH,
      fontSize: 18, fontFace: MONO, bold: true, color: r.color,
      valign: "middle", align: "center", margin: 0,
    });
    s.addText(r.label, {
      x: hx + 1.2, y, w: 2.5, h: rowH,
      fontSize: 13, fontFace: CJK, color: C.TEXT, valign: "middle", margin: 0,
    });
    s.addText(r.decision, {
      x: hx + 3.8, y, w: 1.9, h: rowH,
      fontSize: 12, fontFace: MONO, color: r.color, valign: "middle", margin: 0,
    });
    s.addText(r.tags, {
      x: hx + 5.8, y, w: 6.4, h: rowH,
      fontSize: 11, fontFace: CJK, color: C.TEXT_DIM, valign: "middle", italic: true, margin: 0,
    });
  });

  // footer insight
  s.addText("大模型强制保证 flag 与 decision 一致，并给 1-4 个业务 tags。",
    { x: 0.6, y: 6.55, w: 12.2, h: 0.4,
      fontSize: 13, fontFace: CJK, italic: true, color: C.TEXT_MUTE, align: "center", margin: 0 });

  footer(s); pageNum(s, 14, TOTAL);
}

// ─── Slide 13: 技术核心 4 · 视频抽帧 ────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "技术核心 4 · 短视频抽帧与短路", "AgentCore 原生 · 无需自建容器");

  // left pipeline
  card(s, 0.6, 2.1, 6.0, 4.8);
  s.addText("抽帧链路", {
    x: 0.85, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  const pipeline = [
    { txt: "视频上传 → S3",               color: C.ACC_BLUE },
    { txt: "S3 GetObject",                color: C.TEXT_DIM },
    { txt: "Code Interpreter microVM",    color: C.ACC_MAG },
    { txt: "pip install imageio-ffmpeg",  color: C.TEXT_DIM },
    { txt: "ffmpeg -vf fps=1 抽帧",       color: C.TEXT_DIM },
    { txt: "download_files 取回 JPEG",    color: C.TEXT_DIM },
    { txt: "上传所有帧到 S3",             color: C.TEXT_DIM },
    { txt: "batch=5 并发 → 图像管线",     color: C.ACC_GRN },
  ];
  pipeline.forEach((p, i) => {
    const y = 2.85 + i * 0.45;
    s.addShape(pres.shapes.OVAL, {
      x: 0.95, y: y + 0.1, w: 0.15, h: 0.15,
      fill: { color: p.color }, line: { color: p.color, width: 0 },
    });
    s.addText(p.txt, {
      x: 1.25, y, w: 5.1, h: 0.4,
      fontSize: 12, fontFace: MONO, color: p.color, valign: "middle", margin: 0,
    });
    if (i < pipeline.length - 1) {
      s.addShape(pres.shapes.LINE, {
        x: 1.02, y: y + 0.25, w: 0, h: 0.2,
        line: { color: C.BORDER, width: 1 },
      });
    }
  });

  // right: short-circuit rules
  card(s, 6.8, 2.1, 6.0, 4.8);
  s.addText("短路 + 解读", {
    x: 7.05, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_RED, margin: 0,
  });
  s.addText([
    { text: "任一帧 decision=deny ", options: { bold: true, color: C.ACC_RED } },
    { text: "→ 整段 deny", options: { breakLine: true } },
    { text: "Rekognition 高风险 ≥ 90% ", options: { bold: true, color: C.ACC_RED } },
    { text: "→ 整段 deny", options: { breakLine: true } },
    { text: "", options: { breakLine: true, fontSize: 4 } },
    { text: "命中后：", options: { bold: true, color: C.TEXT, breakLine: true } },
    { text: "• 违规帧单独再跑一次 Nova", options: { breakLine: true } },
    { text: "• 输出「画面内容：XXX。违规原因：XXX」", options: { breakLine: true } },
    { text: "• 聚合关键帧生成视频主题摘要", options: {} },
  ], {
    x: 7.05, y: 2.9, w: 5.5, h: 3.0,
    fontSize: 13, fontFace: CJK, color: C.TEXT_DIM, paraSpaceAfter: 4, margin: 0,
  });

  // bottom callout
  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.05, y: 5.8, w: 5.5, h: 1.0,
    fill: { color: C.BG_PANEL2 }, line: { color: C.ACC_GRN, width: 2 },
  });
  s.addText("全程在 AgentCore 生态内完成", {
    x: 7.2, y: 5.85, w: 5.3, h: 0.4,
    fontSize: 14, fontFace: CJK, bold: true, color: C.ACC_GRN, margin: 0,
  });
  s.addText("无需自建容器 · 无需 Lambda Layer", {
    x: 7.2, y: 6.25, w: 5.3, h: 0.5,
    fontSize: 12, fontFace: CJK, color: C.TEXT_DIM, italic: true, margin: 0,
  });

  footer(s); pageNum(s, 15, TOTAL);
}

// ─── Slide 14: 关键数据 ────────────────────
{
  const s = pres.addSlide();
  bg(s);
  title(s, "关键数据", "延迟 + 成本实测");

  // left: latency table
  card(s, 0.6, 2.1, 6.0, 4.8);
  s.addText("延迟", {
    x: 0.85, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });
  const latRows = [
    ["单图低风险（快筛通过）",   "~10s",   C.ACC_GRN],
    ["单图高风险（Nova+Sonnet）", "~22s",   C.ACC_AMB],
    ["同图 3 法域（共享上游）",   "~25s",   C.ACC_AMB],
    ["30s 视频（无违规）",         "~1-2min", C.ACC_AMB],
    ["30s 视频（首帧违规短路）",   "~15s",   C.ACC_GRN],
  ];
  latRows.forEach((r, i) => {
    const y = 2.9 + i * 0.65;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.85, y, w: 5.5, h: 0.55,
      fill: { color: i % 2 === 0 ? C.BG_PANEL2 : C.BG_PANEL },
      line: { color: C.BORDER, width: 0 },
    });
    s.addText(r[0], {
      x: 0.95, y, w: 3.5, h: 0.55,
      fontSize: 12, fontFace: CJK, color: C.TEXT, valign: "middle", margin: 0,
    });
    s.addText(r[1], {
      x: 4.45, y, w: 1.8, h: 0.55,
      fontSize: 16, fontFace: MONO, bold: true, color: r[2],
      valign: "middle", align: "right", margin: 0,
    });
  });

  // right: cost breakdown
  card(s, 6.8, 2.1, 6.0, 4.8);
  s.addText("成本（us-east-1）", {
    x: 7.05, y: 2.25, w: 5.5, h: 0.5,
    fontSize: 18, fontFace: CJK, bold: true, color: C.ACC_AMB, margin: 0,
  });
  const costRows = [
    ["Rekognition × 2",          "$0.002"],
    ["Haiku 快筛层 × 3",         "$0.003"],
    ["Sonnet 决策（30%）",       "$0.002"],
    ["Nova Pro（20-30%）",       "$0.003"],
    ["CI + Memory",              "<$0.001"],
  ];
  costRows.forEach((r, i) => {
    const y = 2.9 + i * 0.5;
    s.addText(r[0], {
      x: 7.05, y, w: 3.8, h: 0.45,
      fontSize: 12, fontFace: CJK, color: C.TEXT_DIM, valign: "middle", margin: 0,
    });
    s.addText(r[1], {
      x: 10.85, y, w: 1.7, h: 0.45,
      fontSize: 13, fontFace: MONO, color: C.TEXT, valign: "middle", align: "right", margin: 0,
    });
  });
  // totals
  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.05, y: 5.4, w: 5.5, h: 0.05,
    fill: { color: C.ACC_AMB }, line: { color: C.ACC_AMB, width: 0 },
  });
  s.addText("期望总计（per image）", {
    x: 7.05, y: 5.55, w: 3.8, h: 0.45,
    fontSize: 13, fontFace: CJK, bold: true, color: C.TEXT, valign: "middle", margin: 0,
  });
  s.addText("~$0.011", {
    x: 10.85, y: 5.5, w: 1.7, h: 0.55,
    fontSize: 20, fontFace: MONO, bold: true, color: C.ACC_AMB, align: "right", margin: 0,
  });
  s.addText("比「全走 Nova + Sonnet」省约 50%", {
    x: 7.05, y: 6.1, w: 5.5, h: 0.5,
    fontSize: 12, fontFace: CJK, color: C.TEXT_DIM, italic: true, align: "center", margin: 0,
  });

  footer(s); pageNum(s, 16, TOTAL);
}

// ─── Slide 15: 收尾 / 金句 ─────────────────────
{
  const s = pres.addSlide();
  bg(s);

  s.addShape(pres.shapes.OVAL, {
    x: W - 4, y: -4, w: 9, h: 9,
    fill: { color: C.ACC_MAG, transparency: 94 }, line: { color: C.ACC_MAG, width: 0, transparency: 100 },
  });

  s.addText("从「规则引擎」", {
    x: 0.8, y: 1.5, w: W - 1.6, h: 0.9,
    fontSize: 40, fontFace: CJK, bold: true, color: C.TEXT_DIM, margin: 0,
  });
  s.addText("到「智能审核大脑」", {
    x: 0.8, y: 2.35, w: W - 1.6, h: 1.0,
    fontSize: 52, fontFace: CJK, bold: true, color: C.ACC_BLUE, margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 3.55, w: 3.5, h: 0.04,
    fill: { color: C.ACC_GRN }, line: { color: C.ACC_GRN, width: 0 },
  });

  s.addText("Agent 自编排  ·  大模型自解释  ·  记忆自进化", {
    x: 0.8, y: 3.8, w: W - 1.6, h: 0.6,
    fontSize: 22, fontFace: CJK, color: C.ACC_GRN, italic: true, margin: 0,
  });

  s.addText([
    { text: "不仅告诉运营", options: { color: C.TEXT_DIM } },
    { text: "结果", options: { color: C.ACC_AMB, bold: true } },
    { text: "，更解释", options: { color: C.TEXT_DIM } },
    { text: "原因", options: { color: C.ACC_AMB, bold: true } },
    { text: "；", options: { color: C.TEXT_DIM, breakLine: true } },
    { text: "不仅执行", options: { color: C.TEXT_DIM } },
    { text: "策略", options: { color: C.ACC_AMB, bold: true } },
    { text: "，更随业务", options: { color: C.TEXT_DIM } },
    { text: "迭代", options: { color: C.ACC_AMB, bold: true } },
    { text: "。", options: { color: C.TEXT_DIM } },
  ], {
    x: 0.8, y: 4.8, w: W - 1.6, h: 1.5,
    fontSize: 22, fontFace: CJK, margin: 0,
  });

  s.addText("Strands Agents × Amazon Bedrock AgentCore · 2026", {
    x: 0.8, y: H - 0.7, w: W - 1.6, h: 0.4,
    fontSize: 11, fontFace: MONO, color: C.TEXT_MUTE, margin: 0,
  });
}

// ------------------------------------------------------------------ write
pres.writeFile({ fileName: "/Users/hugoxiao/ugc-moderation-agent/docs/UGC-Moderation-Demo.pptx" })
  .then((fn) => console.log("Wrote " + fn))
  .catch((e) => { console.error(e); process.exit(1); });
