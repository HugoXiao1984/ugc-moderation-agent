export type Jurisdiction = "CN" | "EU" | "US";
export type Decision = "allow" | "deny" | "human_review";

export interface OrchestratorOutput {
  modality: string;
  jurisdiction: Jurisdiction;
  prior_risk: "low" | "medium" | "high";
  effective_threshold: number;
  memory_hits: Array<{ memory_id?: string; relevance_score?: number; corrected_decision?: string | null }>;
  memory_rationale: string[];
  routing_hint?: string;
  needs_text_guard?: boolean;
}

export interface FastScreenOutput {
  max_confidence: number;
  labels: Array<{ Name: string; Confidence: number }>;
  has_text: boolean;
  has_person?: boolean;
  trigger_deep_review?: boolean;
}

export interface DeepReviewOutput {
  verdict: Decision;
  confidence: number;
  risk_tags: string[];
  reasoning_cn: string;
  ocr_text?: string;
}

export interface TextGuardOutput {
  action: "NONE" | "GUARDRAIL_INTERVENED";
  blocked_topics: string[];
  blocked_pii?: string[];
}

export interface DecisionOutput {
  decision: Decision;
  reasoning_cn: string;
  violated_rules: string[];
  confidence: number;
  escalation_needed?: boolean;
  jurisdiction: Jurisdiction;
  execution_mode?: string;
  thresholds_used?: Record<string, number>;
  memory_rationale?: string[];
  flag?: number;
  tags?: string[];
}

export interface ModerationReport {
  case_id: string;
  content_s3_uri: string;
  jurisdiction: Jurisdiction;
  orchestrator: OrchestratorOutput;
  fast_screen?: FastScreenOutput | null;
  deep_review?: DeepReviewOutput | null;
  text_guard?: TextGuardOutput | null;
  decision: DecisionOutput;
  trace: string[];
}

export interface TraceSpan {
  span: string;
  start_ms: number;
  dur_ms: number;
  extra: Record<string, unknown>;
}

export interface TraceEvent {
  event: string;
  extra: Record<string, unknown>;
}

export interface TraceResult {
  case_id: string | null;
  spans: TraceSpan[];
  events: TraceEvent[];
}

export interface MetaInfo {
  aws_region: string;
  nova_model_id: string;
  agent_models: Record<string, string>;
  memory_id: string | null;
  guardrail_id: string | null;
  code_interpreter_id: string | null;
  demo_bucket: string;
  default_confidence_threshold: number;
  client_mode: string;
  agent_runtime_arn: string | null;
}

export interface MemoryRecord {
  memory_id: string;
  content: string;
  created_at: string;
}

export interface Sample {
  s3_uri: string;
  label: string;
  kind: "image" | "video";
  scenario: string;
}

export interface FrameResult {
  second: number;
  s3_uri: string;
  decision: Decision;
  confidence: number;
  top_label: string | null;
  reasoning_cn: string;
  risk_tags?: string[];
  flag?: number;
  short_circuit: boolean;
}

export interface VideoModerationReport {
  case_id: string;
  content_s3_uri: string;
  jurisdiction: Jurisdiction;
  verdict: Decision;
  reasoning_cn: string;
  duration_s: number;
  frames_sampled: number;
  frames_evaluated: number;
  offending_frame: FrameResult | null;
  frame_results: FrameResult[];
  summary_cn?: string;
  summary_topic?: string;
  flag?: number;
  tags?: string[];
  elapsed_s: number;
}

export interface VideoLimits {
  max_video_seconds: number;
  frames_per_second: number;
  batch_size: number;
}

export interface VideoProgress {
  case_id: string;
  stage: string;
  stage_label: string;
  frames_done: number;
  frames_total: number;
  elapsed_s: number;
  done: boolean;
  error: string | null;
  verdict?: Decision | null;
}
