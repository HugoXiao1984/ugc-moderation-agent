"""Hybrid pipeline (v2): deterministic Python orchestration + 2 real Agents.

Design motivation: in v1 all 6 nodes are Strands Agents. For I/O steps the
LLM "thinks about whether to call the tool" — wasted latency. In v2 we only
keep LLMs where real reasoning is required:

  - deep_review Agent wraps Nova Pro (multimodal vision reasoning)
  - decision_heavy Agent fuses everything into a human-readable CN ruling

All other work (Memory recall, Rekognition fan-out, threshold routing,
jurisdiction policy script execution) is plain Python calling the same
@tool functions directly (via `.__wrapped__`).

AgentCore components are unchanged: Memory, Code Interpreter, Runtime,
Gateway — all still in play. We just shrunk the set of LLM-powered nodes.

Preserves the ModerationReport schema of pipeline.py so the UI, API and
AgentCore Runtime entrypoint are interchangeable.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from .graph.state import (
    DecisionOutput,
    DeepReviewOutput,
    FastScreenOutput,
    ModerationReport,
    OrchestratorOutput,
    TextGuardOutput,
)
from .memory.session_manager import build_session_manager
from .pipeline import report_to_dict as _report_to_dict  # re-export
from .settings import get_settings
from .tools.code_interpreter_tool import run_jurisdiction_policy
from .tools.guardrail_tool import apply_guardrail
from .tools.memory_tool import recall_similar_cases
from .tools.nova_vision_tool import _fetch as _fetch_from_s3
from .tools.nova_vision_tool import analyze_with_nova
from .tools.rekognition_tool import detect_labels, detect_moderation_labels
from .util.logging import get_logger
from .util.media import resize_for_nova
from .util.tracing import log_event, set_case, span

log = get_logger(__name__)

# Unwrap @tool decorators so we can call the plain Python functions in-process
# without going through Strands' tool-invocation plumbing.
_recall_similar = recall_similar_cases.__wrapped__
_detect_mod = detect_moderation_labels.__wrapped__
_detect_general = detect_labels.__wrapped__
_apply_guardrail = apply_guardrail.__wrapped__
_run_policy = run_jurisdiction_policy.__wrapped__


HIGH_RISK_LABEL_NAMES = {
    "Explicit Nudity",
    "Non-Explicit Nudity of Intimate parts and Kissing",
    "Violence",
    "Graphic Violence",
    "Visually Disturbing",
    "Hate Symbols",
}

# Labels that a Memory recall is allowed to override (borderline / contextual
# risk — e.g. gym/yoga/swimwear content tagged "Suggestive" or "Non-Explicit
# Nudity"). The hard red-lines below are deliberately *excluded*: an operator
# misjudgment on those still demands real human review, so recall never
# auto-flips them. This is what keeps a 92% Explicit Nudity image DENY while
# flipping a 96% Non-Explicit-Nudity bodybuilder image to ALLOW.
#
# Note: "Non-Explicit Nudity of Intimate parts and Kissing" stays in
# HIGH_RISK_LABEL_NAMES (so it still triggers deep review) *and* lives here
# (so memory may flip it) — the two sets serve different purposes.
_HARD_REDLINE_LABELS = {
    "Explicit Nudity",
    "Graphic Violence",
    "Visually Disturbing",
    "Hate Symbols",
    "Violence",
}
_OVERRIDABLE_LABELS = {
    "Suggestive",
    "Non-Explicit Nudity of Intimate parts and Kissing",
    "Non-Explicit Nudity",
    "Exposed Male Nipple",
    "Female Swimwear Or Underwear",
    "Male Swimwear Or Underwear",
    "Swimwear or Underwear",
    "Revealing Clothes",
    "Alcohol",
    "Alcoholic Beverages",
    "Gambling",
    "Smoking",
    "Drugs & Tobacco Paraphernalia",
}


def _apply_memory_override(
    policy: dict[str, Any],
    orch: OrchestratorOutput,
    signals: dict[str, Any],
) -> dict[str, Any]:
    """Let a strong Memory recall flip a borderline ruling.

    This is the demonstrable payoff of the 'misjudgment → learn → readjust'
    loop. The orchestrator has already moved `effective_threshold` based on
    recall; here we turn that into an actual decision change:

      - Relax (threshold raised, e.g. 75→85 after recalling an
        allow-misjudgment): if the content was denied *only* on overridable
        labels (no hard red-line), flip deny → allow.
      - Tighten (threshold lowered, e.g. 75→65 after a deny-misjudgment): if
        the content was allowed but an overridable label is elevated, flip
        allow → human_review.

    Keyword/guardrail denies and any hard red-line label are never touched.
    Returns the (possibly replaced) policy dict; adds a `memory_override` key
    when a flip occurred.
    """
    default = get_settings().default_confidence_threshold
    eff = orch.effective_threshold
    decision = policy.get("decision")

    # --- relax: deny → allow ---
    if eff > default + 1 and decision == "deny":
        # On a label-threshold deny, cn/eu/us.py set thresholds_used to exactly
        # the violated labels; a red-line keyword deny sets {"red_line": ...}.
        violated = [n for n in (policy.get("thresholds_used") or {}) if n != "red_line"]
        if violated and all(v in _OVERRIDABLE_LABELS for v in violated):
            note = (
                f"命中相似历史误判记忆（运营曾将同类内容更正为 allow），"
                f"且违规仅来自边缘标签 {violated}（非色情/血腥等硬红线），"
                f"依记忆放宽阈值（{default:g}→{eff:g}）改判为 allow。"
            )
            orch.memory_rationale.append(f"【记忆改判】deny → allow：{note}")
            return {
                **policy,
                "decision": "allow",
                "reasoning_cn": note,
                "violated_rules": [],
                "confidence": 0.8,
                "escalation_needed": False,
                "memory_override": "deny->allow",
            }

    # --- tighten: allow → human_review ---
    if eff < default - 1 and decision == "allow":
        max_conf = float(signals.get("max_confidence") or 0.0)
        present = [
            l.get("Name") for l in (signals.get("labels") or [])
            if l.get("Name") in _OVERRIDABLE_LABELS
        ]
        if present and max_conf >= eff - 5:
            note = (
                f"命中相似历史漏判记忆（运营曾将同类内容更正为 deny），"
                f"边缘标签 {present} 置信度偏高（max={max_conf:g}），"
                f"依记忆收紧阈值（{default:g}→{eff:g}）转人工复核。"
            )
            orch.memory_rationale.append(f"【记忆改判】allow → human_review：{note}")
            return {
                **policy,
                "decision": "human_review",
                "reasoning_cn": note,
                "escalation_needed": True,
                "confidence": 0.7,
                "memory_override": "allow->human_review",
            }

    return policy


# --------------------------------------------------------------------- steps

def _orchestrate(content_s3_uri: str, jurisdiction: str, actor: str) -> OrchestratorOutput:
    """Deterministic orchestrator: Memory recall + threshold adjustment.

    Replaces the orchestrator Agent. Memory recall is still an AgentCore API
    call — the LLM was only being used here to call that tool and pick a
    threshold from a lookup table. That's now a plain if/elif.
    """
    summary = f"待审核 UGC 图像 {content_s3_uri}"
    with span("step:memory.recall", jurisdiction=jurisdiction):
        hits = _recall_similar(
            case_summary=summary,
            jurisdiction=jurisdiction,
            actor_id=actor,
            top_k=3,
        ) or []

    default = get_settings().default_confidence_threshold
    threshold = default
    rationale: list[str] = []

    # Semantic-strategy scores for genuinely similar cases land around
    # 0.35-0.45 in practice (the strategy rewrites text, lowering cosine
    # similarity), so a 0.75 gate never fires. Tune at MEMORY_RELEVANCE_GATE.
    #
    # The strategy also splits one misjudgment into several records — a
    # "content description" record (no corrected decision) plus a separate
    # "correction" record. The top-scored hit is often the description one,
    # so pick the highest-scoring hit above the gate that actually carries a
    # corrected decision, rather than blindly taking hits[0].
    gate = get_settings().memory_relevance_gate
    above_gate = sorted(
        (h for h in hits if (h.get("relevance_score") or 0) >= gate),
        key=lambda h: h.get("relevance_score") or 0,
        reverse=True,
    )
    top = next(
        (h for h in above_gate if (h.get("corrected_decision") or "").lower() in ("allow", "deny")),
        None,
    )
    if top:
        corrected = (top.get("corrected_decision") or "").lower()
        if corrected == "allow":
            threshold = 85.0
            rationale.append(
                f"命中相似误判（运营更正为 allow, 相关度 {top.get('relevance_score'):.2f}），"
                f"阈值从 {default} 放宽到 {threshold}"
            )
        elif corrected == "deny":
            threshold = 65.0
            rationale.append(
                f"命中相似漏判（运营更正为 deny, 相关度 {top.get('relevance_score'):.2f}），"
                f"阈值从 {default} 收紧到 {threshold}"
            )

    return OrchestratorOutput(
        modality="image",
        jurisdiction=jurisdiction,
        prior_risk="medium" if not hits else "high",
        effective_threshold=threshold,
        memory_hits=[
            {
                "memory_id": h.get("memory_id"),
                "relevance_score": h.get("relevance_score"),
                "corrected_decision": h.get("corrected_decision"),
            }
            for h in hits
        ],
        memory_rationale=rationale,
        routing_hint=(
            f"阈值={threshold}，历史命中 {len(hits)} 条" if hits else "无历史命中，用默认阈值"
        ),
        needs_text_guard=False,
    )


def _fetch_and_resize(s3_uri: str) -> bytes | None:
    """Fetch image from S3 once and resize to Nova-ready JPEG bytes."""
    try:
        with span("step:image.fetch+resize", s3_uri=s3_uri):
            return resize_for_nova(_fetch_from_s3(s3_uri))
    except Exception as exc:       # noqa: BLE001
        log.warning("pre-fetch failed", extra={"ctx_err": str(exc)[:200]})
        return None


async def _fast_screen_and_prefetch(s3_uri: str) -> tuple[FastScreenOutput, bytes | None]:
    """Run Rekognition AND pre-fetch image bytes in parallel.

    Rekognition goes over the AWS control plane with an S3 URI (internal,
    fast); the raw S3 GetObject for Nova goes public-internet. By running
    them concurrently the S3 latency is hidden behind Rekognition.
    """
    loop = asyncio.get_event_loop()
    with span("step:fast_screen"):
        mod_res, gen_res, image_bytes = await asyncio.gather(
            loop.run_in_executor(None, _detect_mod, s3_uri),
            loop.run_in_executor(None, _detect_general, s3_uri),
            loop.run_in_executor(None, _fetch_and_resize, s3_uri),
        )

    labels = mod_res.get("labels", []) or []
    names = {lab.get("Name") for lab in labels}
    high_risk_hit = bool(names & HIGH_RISK_LABEL_NAMES)
    fs = FastScreenOutput(
        max_confidence=float(mod_res.get("max_confidence") or 0.0),
        labels=[{"Name": lab.get("Name"), "Confidence": lab.get("Confidence")} for lab in labels],
        has_text=bool(gen_res.get("has_text")),
        has_person=bool(gen_res.get("has_person")),
        trigger_deep_review=high_risk_hit,
    )
    return fs, image_bytes


def _needs_deep_review(fs: FastScreenOutput, threshold: float) -> bool:
    if fs.max_confidence >= threshold:
        return True
    if any(lab.get("Name") in HIGH_RISK_LABEL_NAMES for lab in fs.labels):
        return True
    if 60 <= fs.max_confidence < threshold and fs.trigger_deep_review:
        return True
    return False


_analyze_with_nova = analyze_with_nova.__wrapped__


def _run_deep_review_agent(
    s3_uri: str,
    jurisdiction: str,
    hint: str,
    image_bytes: bytes | None = None,
) -> DeepReviewOutput | None:
    """Deep review: Nova Pro multimodal reasoning.

    When image_bytes is provided (hybrid pipeline pre-fetches once), we skip
    the S3 GetObject inside the Nova tool — saves an entire cross-region
    round-trip on the failure-prone public-internet path.
    """
    with span("step:deep_review.nova", jurisdiction=jurisdiction):
        parsed = _analyze_with_nova(
            s3_uri=s3_uri,
            jurisdiction=jurisdiction,
            hint=hint,
            image_bytes=image_bytes,
        )
    if not parsed:
        return None
    try:
        return DeepReviewOutput.model_validate(parsed)
    except Exception as exc:       # noqa: BLE001
        log.warning("deep_review schema invalid", extra={"ctx_err": str(exc)[:200]})
        return None


def _text_guard(text: str) -> TextGuardOutput | None:
    if not text.strip():
        return None
    with span("step:text_guard"):
        res = _apply_guardrail(text=text)
    return TextGuardOutput(
        action=res.get("action") or "NONE",
        blocked_topics=res.get("blocked_topics") or [],
        blocked_pii=res.get("blocked_pii") or [],
    )


def _build_signals(
    fs: FastScreenOutput,
    dr: DeepReviewOutput | None,
    tg: TextGuardOutput | None,
    orch: OrchestratorOutput,
) -> dict[str, Any]:
    return {
        "labels": [{"Name": l["Name"], "Confidence": l["Confidence"]} for l in fs.labels],
        "max_confidence": fs.max_confidence,
        "has_text": fs.has_text,
        "nova": (
            {
                "verdict": dr.verdict,
                "confidence": dr.confidence,
                "risk_tags": dr.risk_tags,
                "reasoning_cn": dr.reasoning_cn,
            }
            if dr
            else None
        ),
        "ocr_text": dr.ocr_text if dr else "",
        "guardrail": (
            {"action": tg.action, "blocked_topics": tg.blocked_topics, "blocked_pii": tg.blocked_pii}
            if tg
            else None
        ),
        "orchestrator_hints": {
            "effective_threshold": orch.effective_threshold,
            "memory_rationale": orch.memory_rationale,
        },
    }


def _decision_light(
    jurisdiction: str,
    signals: dict[str, Any],
    orch: OrchestratorOutput,
) -> DecisionOutput:
    """Fast path: no LLM. Call Code Interpreter and wrap the PolicyResult."""
    with span("step:decision_light.policy", jurisdiction=jurisdiction):
        policy = _run_policy(jurisdiction=jurisdiction, signals=signals)
    policy = _apply_memory_override(policy, orch, signals)
    reasoning = (
        f"内容通过 {jurisdiction} 法域默认阈值（{orch.effective_threshold}），"
        f"未命中任何高风险标签。"
    )
    d = policy.get("decision", "allow")
    return DecisionOutput(
        decision=d,
        reasoning_cn=policy.get("reasoning_cn") or reasoning,
        violated_rules=policy.get("violated_rules", []),
        confidence=float(policy.get("confidence", 0.85)),
        escalation_needed=bool(policy.get("escalation_needed", False)),
        jurisdiction=jurisdiction,       # type: ignore[arg-type]
        execution_mode=policy.get("execution_mode", "code_interpreter"),
        thresholds_used=policy.get("thresholds_used", {}),
        memory_rationale=orch.memory_rationale,
        flag=_default_flag_for(d),
        tags=policy.get("violated_rules", [])[:3],
    )


def _default_flag_for(decision: str) -> int:
    """Pick a reasonable default flag when Sonnet didn't supply one.

    Conservative: on human_review default to 100 (lightest review tier) and
    deny to 999 (highest severity) — we'd rather over-flag on fallback than
    under-flag.
    """
    return {"deny": 999, "human_review": 100, "allow": 1}.get(decision, 1)


def _run_decision_heavy_agent(
    jurisdiction: str,
    signals: dict[str, Any],
    orch: OrchestratorOutput,
) -> DecisionOutput:
    """Sonnet synthesizes a human-readable CN ruling.

    We pre-compute the PolicyResult in Python (one direct Code Interpreter call)
    and hand it to Sonnet as context. Sonnet does only one LLM round-trip — no
    tool_use, no second call — just "turn this structured verdict into natural
    Chinese reasoning." This drops a second CI call + an extra LLM round.
    """
    from strands import Agent
    from strands.models import BedrockModel

    from .settings import get_settings as _s

    settings = _s()

    # Pre-compute PolicyResult — one deterministic Code Interpreter call.
    with span("step:decision_heavy.policy", jurisdiction=jurisdiction):
        policy = _run_policy(jurisdiction=jurisdiction, signals=signals)
    # Apply the Memory-driven flip *before* handing the verdict to Sonnet, so
    # the LLM synthesizes reasoning around the corrected decision rather than
    # the raw policy ruling.
    policy = _apply_memory_override(policy, orch, signals)

    # Give the Agent everything it needs as context; no tools to call.
    system = """你是 UGC 审核决策 Agent。根据我提供的 PolicyResult + 上游信号合成最终 JSON 输出。
不要调用任何工具。直接输出 JSON：

{
  "decision": "allow|deny|human_review",  // 取 PolicyResult.decision
  "reasoning_cn": "<2~4 句给运营看的中文理由：先概述内容（从 nova 或 labels 推断），再说快筛/Nova 发现，再说命中/未命中的规则与阈值，最后说 Memory 调整记录>",
  "violated_rules": [...],                 // 来自 PolicyResult
  "confidence": <float>,
  "escalation_needed": <bool>,
  "jurisdiction": "...",
  "execution_mode": "...",                 // 来自 PolicyResult
  "thresholds_used": {...},
  "memory_rationale": [...],               // 来自 orchestrator.memory_rationale
  "flag": <int>,                           // 违规等级，见下表
  "tags": ["<细粒度风险标签，英文或中文皆可>", ...]
}

flag 取值规则（与 decision 并存，不冲突）：
  999 — 最严重违规：色情 / 卡通色情 / 血腥暴力 / 引导性广告 / 未成年涉风险
  998 — 次严重违规：枪支武器 / 毒品 / 恐怖反感 / 冒犯宗教信仰
  997 — 特殊文化背景冒犯：牛肉（印度）/ 敏感宗教/种姓/政治话题 / 性话题 / 暴力血腥
  200 — 疑似未成年 (15~18 岁)
  100 — 普通违规：吸烟饮酒 / 诋毁/侮辱 / 脏话
    1 — 不处理：性感动作/自拍（非色情）/ 卡通未成年形象（非色情）
    2 — 内容完全不可辨识

flag 与 decision 的一致性约束：
  - decision=="deny" → flag ∈ {999, 998}
  - decision=="human_review" → flag ∈ {997, 200, 100}
  - decision=="allow" → flag ∈ {1, 2}

tags 要求：给 1~4 个细粒度标签（例："色情"/"血腥暴力"/"未成年"/"吸烟"/"广告引导"/"宗教敏感"），用于运营看板筛选。

只输出 JSON。"""
    model = BedrockModel(
        model_id=settings.model_for("decision_heavy"), region_name=settings.aws_region
    )
    agent = Agent(name="decision_heavy", model=model, system_prompt=system, tools=[])

    context = json.dumps(
        {
            "jurisdiction": jurisdiction,
            "signals": signals,
            "policy_result": policy,
            "memory_rationale": orch.memory_rationale,
        },
        ensure_ascii=False,
    )
    prompt = f"上下文（PolicyResult + signals）：\n{context}\n\n请合成最终 JSON。"
    with span("step:decision_heavy.agent", jurisdiction=jurisdiction):
        result = agent(prompt)

    raw = str(getattr(result, "message", result) or "")
    blob = _last_json(raw)
    if not blob:
        log.warning("decision_heavy agent returned no JSON; using policy directly")
        d = policy.get("decision", "human_review")
        return DecisionOutput(
            decision=d,
            reasoning_cn=policy.get("reasoning_cn") or "决策 Agent 未返回结构化输出，使用策略脚本原始裁决。",
            confidence=float(policy.get("confidence", 0.5)),
            jurisdiction=jurisdiction,       # type: ignore[arg-type]
            execution_mode=policy.get("execution_mode", "local_fallback"),
            thresholds_used=policy.get("thresholds_used", {}),
            memory_rationale=orch.memory_rationale,
            flag=_default_flag_for(d),
            tags=policy.get("violated_rules", [])[:3],
        )
    # Backfill any fields the Agent may have omitted, favoring policy as source of truth.
    blob.setdefault("jurisdiction", jurisdiction)
    blob.setdefault("memory_rationale", orch.memory_rationale)
    blob.setdefault("execution_mode", policy.get("execution_mode", "code_interpreter"))
    blob.setdefault("thresholds_used", policy.get("thresholds_used", {}))
    blob.setdefault("violated_rules", policy.get("violated_rules", []))
    blob.setdefault("confidence", float(policy.get("confidence", 0.7)))
    blob.setdefault("escalation_needed", bool(policy.get("escalation_needed", False)))
    # flag/tags 由 Sonnet 输出；若缺失或不合规，按 decision 回填一个默认值
    blob.setdefault("flag", _default_flag_for(blob.get("decision", "human_review")))
    blob.setdefault("tags", blob.get("violated_rules", [])[:3])
    try:
        return DecisionOutput.model_validate(blob)
    except Exception as exc:       # noqa: BLE001
        log.warning("decision schema invalid after backfill", extra={"ctx_err": str(exc)[:200]})
        d = policy.get("decision", "human_review")
        return DecisionOutput(
            decision=d,
            reasoning_cn=blob.get("reasoning_cn") or policy.get("reasoning_cn", "(无)"),
            confidence=float(policy.get("confidence", 0.6)),
            jurisdiction=jurisdiction,       # type: ignore[arg-type]
            execution_mode=policy.get("execution_mode", "code_interpreter"),
            thresholds_used=policy.get("thresholds_used", {}),
            violated_rules=policy.get("violated_rules", []),
            escalation_needed=bool(policy.get("escalation_needed", False)),
            memory_rationale=orch.memory_rationale,
            flag=_default_flag_for(d),
            tags=policy.get("violated_rules", [])[:3],
        )


def _last_json(text: str) -> dict[str, Any]:
    """Extract the last balanced { ... } JSON object from free text."""
    start, depth, in_str, esc = -1, 0, False, False
    last = None
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start:i + 1]
                try:
                    last = json.loads(chunk)
                except json.JSONDecodeError:
                    pass
                start = -1
    return last or {}


# --------------------------------------------------------------------- entry

async def run_moderation_hybrid(
    content_s3_uri: str,
    jurisdiction: str = "CN",
    tenant_id: str | None = None,
    session_id: str | None = None,
    ocr_text: str = "",
) -> ModerationReport:
    settings = get_settings()
    actor = tenant_id or settings.demo_tenant_id
    sid = session_id or str(uuid.uuid4())
    case_id = f"case-{sid[:8]}"
    set_case(case_id)

    trace: list[str] = []
    log_event(case_id, "invocation.start",
              content_s3_uri=content_s3_uri, jurisdiction=jurisdiction, engine="hybrid")

    with span("pipeline", case_id, jurisdiction=jurisdiction,
              content_s3_uri=content_s3_uri, engine="hybrid"):
        with span("build_session_manager", case_id):
            sm_ctx = build_session_manager(actor, sid, jurisdiction)
            sm_ctx.__enter__()
        try:
            # Step 1 — orchestrate (Memory recall + threshold)
            orch = _orchestrate(content_s3_uri, jurisdiction, actor)
            trace.append("orchestrator")

            # Step 2 — fast_screen (Rekognition ×2) + pre-fetch image bytes in parallel
            fs, image_bytes = await _fast_screen_and_prefetch(content_s3_uri)
            trace.append("fast_screen")

            # Step 3 — text_guard if any text present
            tg: TextGuardOutput | None = None
            text_for_guard = ocr_text
            if text_for_guard or fs.has_text:
                tg = _text_guard(text_for_guard or "(图像中检测到文字)")
                if tg:
                    trace.append("text_guard")

            # Step 4 — deep_review (real Agent) only when required
            # Uses bytes pre-fetched above — no second S3 round-trip.
            dr: DeepReviewOutput | None = None
            if _needs_deep_review(fs, orch.effective_threshold):
                hint = (
                    f"快筛 max_confidence={fs.max_confidence:.1f}, "
                    f"labels={[l['Name'] for l in fs.labels][:3]}"
                )
                dr = _run_deep_review_agent(
                    content_s3_uri, jurisdiction, hint, image_bytes=image_bytes
                )
                if dr:
                    trace.append("deep_review")

            # Step 5 — decision
            signals = _build_signals(fs, dr, tg, orch)
            if dr is None and (tg is None or tg.action == "NONE") and \
               fs.max_confidence < orch.effective_threshold:
                # Low-risk fast path: no LLM
                decision = _decision_light(jurisdiction, signals, orch)
                trace.append("decision_light")
            else:
                decision = _run_decision_heavy_agent(jurisdiction, signals, orch)
                trace.append("decision_heavy")

        finally:
            sm_ctx.__exit__(None, None, None)

    log_event(case_id, "invocation.end",
              decision=decision.decision, trace=trace, engine="hybrid")

    return ModerationReport(
        case_id=case_id,
        content_s3_uri=content_s3_uri,
        jurisdiction=jurisdiction,       # type: ignore[arg-type]
        orchestrator=orch,
        fast_screen=fs,
        deep_review=dr,
        text_guard=tg,
        decision=decision,
        trace=trace,
    )


def run_moderation_hybrid_sync(**kwargs) -> ModerationReport:
    return asyncio.run(run_moderation_hybrid(**kwargs))


# ---------------------------------------------------------------- replay
# Fast path for the Memory-loop demo: after marking a misjudgment, re-running
# the same image is 95% the same work (Rekognition/Nova labels don't change).
# Only Memory recall + the decision stage need to re-run. This skips S3 +
# Rekognition + Nova entirely and typically completes in ~8s instead of ~25s.

async def run_moderation_replay(
    previous_report: ModerationReport,
    tenant_id: str | None = None,
    session_id: str | None = None,
) -> ModerationReport:
    """Re-decide using cached upstream signals + fresh Memory recall.

    Use case: operator marks a case as misjudgment, then re-runs the same
    image to verify the threshold adjustment took effect. We keep the
    cached fast_screen / deep_review / text_guard from the prior report
    and only re-run:
      1. Memory recall (picks up the new misjudgment record)
      2. Decision stage (gets new threshold, re-runs policy + reasoning)
    """
    settings = get_settings()
    actor = tenant_id or settings.demo_tenant_id
    sid = session_id or str(uuid.uuid4())
    case_id = f"case-{sid[:8]}-replay"
    set_case(case_id)

    jurisdiction = previous_report.jurisdiction
    fs = previous_report.fast_screen
    dr = previous_report.deep_review
    tg = previous_report.text_guard

    log_event(case_id, "invocation.start",
              content_s3_uri=previous_report.content_s3_uri,
              jurisdiction=jurisdiction, engine="hybrid_replay",
              prior_case_id=previous_report.case_id)

    trace: list[str] = ["orchestrator (replay)"]

    with span("pipeline", case_id, jurisdiction=jurisdiction,
              content_s3_uri=previous_report.content_s3_uri,
              engine="hybrid_replay"):
        with span("build_session_manager", case_id):
            sm_ctx = build_session_manager(actor, sid, jurisdiction)
            sm_ctx.__enter__()
        try:
            # Step 1 (only live step) — fresh Memory recall + threshold
            orch = _orchestrate(previous_report.content_s3_uri, jurisdiction, actor)

            if fs is not None:
                trace.append("fast_screen (cached)")
            if tg is not None:
                trace.append("text_guard (cached)")
            if dr is not None:
                trace.append("deep_review (cached)")

            # Step 5 — decision with cached signals + new orch.threshold
            # We must have fast_screen at minimum; without it default to safe deny/review.
            if fs is None:
                decision = DecisionOutput(
                    decision="human_review",
                    reasoning_cn="Replay 模式缺失快筛信号，保守转人审。",
                    confidence=0.4,
                    jurisdiction=jurisdiction,  # type: ignore[arg-type]
                    execution_mode="local_fallback",
                    memory_rationale=orch.memory_rationale,
                )
                trace.append("decision_fallback")
            else:
                signals = _build_signals(fs, dr, tg, orch)
                if dr is None and (tg is None or tg.action == "NONE") and \
                   fs.max_confidence < orch.effective_threshold:
                    decision = _decision_light(jurisdiction, signals, orch)
                    trace.append("decision_light")
                else:
                    decision = _run_decision_heavy_agent(jurisdiction, signals, orch)
                    trace.append("decision_heavy")
        finally:
            sm_ctx.__exit__(None, None, None)

    log_event(case_id, "invocation.end",
              decision=decision.decision, trace=trace, engine="hybrid_replay")

    return ModerationReport(
        case_id=case_id,
        content_s3_uri=previous_report.content_s3_uri,
        jurisdiction=jurisdiction,  # type: ignore[arg-type]
        orchestrator=orch,
        fast_screen=fs,
        deep_review=dr,
        text_guard=tg,
        decision=decision,
        trace=trace,
    )


# -------------------------------------------------------- multi-jurisdiction
# The trick: for a single image, the *upstream* signals (Memory recall,
# Rekognition labels, Nova reasoning, text_guard) are jurisdiction-agnostic.
# Only the *decision stage* (policy script + Sonnet reasoning synthesis)
# needs to run per jurisdiction. Share upstream, fan out downstream.

async def run_moderation_hybrid_multi(
    content_s3_uri: str,
    jurisdictions: list[str],
    tenant_id: str | None = None,
    session_id: str | None = None,
    ocr_text: str = "",
    on_ready=None,  # optional async callback: (jurisdiction, ModerationReport)
) -> dict[str, ModerationReport]:
    """Run 3 jurisdictions sharing upstream Memory/Rekognition/Nova/TextGuard.

    Only the decision stage (Code Interpreter policy + Sonnet reasoning) is
    fanned out. Expected wall-clock: ~max(upstream) + max(decision_heavy) —
    roughly 25-28s vs 3× 25s serial or 45-60s naive parallel.

    If `on_ready` is provided, it is called as soon as each jurisdiction's
    decision completes, enabling streaming UX.
    """
    settings = get_settings()
    actor = tenant_id or settings.demo_tenant_id
    sid = session_id or str(uuid.uuid4())
    case_id = f"case-{sid[:8]}-multi"
    set_case(case_id)

    log_event(case_id, "invocation.start",
              content_s3_uri=content_s3_uri, engine="hybrid_multi",
              jurisdictions=jurisdictions)

    # Shared upstream context (use the first jurisdiction for Memory namespace;
    # misjudgment_namespace() ignores jurisdiction anyway in current impl).
    primary_j = jurisdictions[0] if jurisdictions else "CN"

    with span("pipeline", case_id, engine="hybrid_multi",
              content_s3_uri=content_s3_uri,
              jurisdictions=",".join(jurisdictions)):
        with span("build_session_manager", case_id):
            sm_ctx = build_session_manager(actor, sid, primary_j)
            sm_ctx.__enter__()
        try:
            # ---------- SHARED upstream (runs once total) ----------
            orch = _orchestrate(content_s3_uri, primary_j, actor)
            fs, image_bytes = await _fast_screen_and_prefetch(content_s3_uri)

            tg: TextGuardOutput | None = None
            if ocr_text or fs.has_text:
                tg = _text_guard(ocr_text or "(图像中检测到文字)")

            dr: DeepReviewOutput | None = None
            if _needs_deep_review(fs, orch.effective_threshold):
                hint = (f"快筛 max_confidence={fs.max_confidence:.1f}, "
                        f"labels={[l['Name'] for l in fs.labels][:3]}")
                dr = _run_deep_review_agent(
                    content_s3_uri, primary_j, hint, image_bytes=image_bytes
                )

            signals = _build_signals(fs, dr, tg, orch)

            # ---------- PER-JURISDICTION decision (concurrent) ----------
            results: dict[str, ModerationReport] = {}
            loop = asyncio.get_event_loop()

            async def _decide_one(j: str) -> tuple[str, ModerationReport]:
                """Run decision stage for one jurisdiction in a thread.

                Runs in executor because _decision_light / _decision_heavy
                are blocking (Code Interpreter + Bedrock synchronous calls).
                """
                # Build a jurisdiction-specific orchestrator view so the
                # report's jurisdiction field is correct.
                j_orch = OrchestratorOutput(
                    modality=orch.modality,
                    jurisdiction=j,          # type: ignore[arg-type]
                    prior_risk=orch.prior_risk,
                    effective_threshold=orch.effective_threshold,
                    memory_hits=orch.memory_hits,
                    memory_rationale=orch.memory_rationale,
                    routing_hint=orch.routing_hint,
                    needs_text_guard=orch.needs_text_guard,
                )
                # Reuse the same signals dict — it's jurisdiction-agnostic.
                if dr is None and (tg is None or tg.action == "NONE") and \
                   fs.max_confidence < orch.effective_threshold:
                    decision = await loop.run_in_executor(
                        None, _decision_light, j, signals, j_orch
                    )
                    trace_j = ["orchestrator", "fast_screen", "decision_light"]
                else:
                    decision = await loop.run_in_executor(
                        None, _run_decision_heavy_agent, j, signals, j_orch
                    )
                    trace_j = ["orchestrator", "fast_screen"]
                    if tg:
                        trace_j.append("text_guard")
                    if dr:
                        trace_j.append("deep_review")
                    trace_j.append("decision_heavy")

                rep = ModerationReport(
                    case_id=f"{case_id}-{j}",
                    content_s3_uri=content_s3_uri,
                    jurisdiction=j,          # type: ignore[arg-type]
                    orchestrator=j_orch,
                    fast_screen=fs,
                    deep_review=dr,
                    text_guard=tg,
                    decision=decision,
                    trace=trace_j,
                )
                if on_ready is not None:
                    try:
                        await on_ready(j, rep)
                    except Exception as exc:        # noqa: BLE001
                        log.warning("on_ready cb failed",
                                    extra={"ctx_err": str(exc)[:200]})
                return j, rep

            pairs = await asyncio.gather(*[_decide_one(j) for j in jurisdictions])
            for j, rep in pairs:
                results[j] = rep

        finally:
            sm_ctx.__exit__(None, None, None)

    log_event(case_id, "invocation.end",
              engine="hybrid_multi",
              decisions={j: r.decision.decision for j, r in results.items()})
    return results


# Re-export so callers can `from .pipeline_hybrid import report_to_dict`
report_to_dict = _report_to_dict
