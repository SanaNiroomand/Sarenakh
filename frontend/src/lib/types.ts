export type User = { id: number; email: string; name: string };

export type Axes = {
  need: number;
  product_fit: number;
  urgency: number;
  buying_intent: number;
  reachability: number;
  confidence: number;
};

export type Profile = {
  product_name: string;
  one_liner: string;
  persona: string;
  pain_points: string[];
  buying_signals: string[];
  signal_examples: string[];
  disqualifiers: string[];
  reply_tone: string;
  ideal_shape: Axes;
  facts: string[];
};

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type Product = {
  id: number;
  name: string;
  description: string;
  sample_key: string | null;
  profile: Profile | null;
  setup_chat: ChatTurn[];
  turn_cost_usd?: number;
};

export type SampleProduct = { key: string; name: string; emoji: string; pitch: string; description: string };

export type Dataset = {
  id: number;
  name: string;
  source: string;
  sample_key: string | null;
  stats: {
    messages: number;
    analyzable: number;
    authors: number;
    replies: number;
    langs: Record<string, number>;
    first: string | null;
    last: string | null;
  };
  warnings: string[];
};

export type ChatMsg = {
  msg_id: number;
  date: string;
  author: string;
  author_id: string;
  text: string;
  reply_to: number | null;
  kind: string;
  lang: string;
  forwarded_from: string | null;
};

export type RunSummary = {
  id: number;
  status: "queued" | "running" | "done" | "failed" | "stopped";
  budget_usd: number;
  cost_usd: number;
  saved_usd: number;
  stop_reason: string | null;
  error: string | null;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  product: { id: number; name: string; sample_key: string | null } | null;
  dataset: { id: number; name: string; sample_key: string | null } | null;
  leads: number | null;
  scanned: number | null;
  duration_s: number | null;
  replay: boolean;
};

export type AgentEvent = {
  seq: number;
  ts: number;
  type: string;
  msg_id: number | null;
  text: string;
  data: Record<string, any>;
  cost_usd: number;
};

export type Temperature = "hot" | "warm" | "cold";

export type Reply = {
  reply: string;
  mode: "pure_help" | "help_soft_mention";
  facts_used: string[];
  help_points: string[];
  check: { ok: boolean; issues: string[] };
  revised: boolean;
};

export type TraceStep = { tool: string; args: Record<string, any>; step: number };

export type LeadItem = {
  msg_id: number;
  author: string;
  author_id: string;
  date: string;
  text: string;
  lang: string;
  decision: "lead" | "watch" | "rejected" | "skipped" | "pending";
  why_not: string | null;
  stage: string;
  triage: { signal: string; relevance: number; reason: string } | null;
  fit: number | null;
  cached: boolean;
  cost_usd: number;
  equiv_cost_usd: number;
  scores?: Axes;
  temperature?: Temperature;
  weak?: { axis: keyof Axes; label: string; score: number };
  verdict?: {
    stated_need: string;
    reasoning: string;
    timing: "browsing" | "considering" | "ready";
    action: "reply" | "dm" | "watch" | "skip";
    disqualifiers_found: string[];
    thread_resolved: boolean;
    evidence_msg_ids: number[];
  };
  evidence?: { msg_id: number; author: string; date: string; text: string }[];
  reply?: Reply | null;
  critic?: { strongest_objection: string; survives: boolean; reason: string } | null;
  trace?: TraceStep[];
  vote?: number;
  relevance?: number;
};

export type OpportunityPoint = {
  msg_id: number;
  author: string;
  decision: string;
  kind: "investigated" | "triage";
  cost: number;
  quality: number;
  temperature: number;
};

export type Results = {
  run: RunSummary;
  stats: Record<string, any>;
  ideal_shape: Axes | null;
  product_name: string | null;
  kpi: {
    scanned: number;
    leads: number;
    cost_usd: number;
    equivalent_cost_usd: number;
    cost_per_lead_usd: number | null;
    saved_usd: number;
  };
  funnel: { stage: string; label: string; count: number; cost: number }[];
  burn: { n: number; cost: number; equiv_cost: number; leads: number }[];
  leads: LeadItem[];
  watch: LeadItem[];
  rejected: LeadItem[];
  opportunity: OpportunityPoint[];
};

export type Evaluation = {
  run_id: number;
  product: string;
  real_leads: number;
  found: number;
  false_positives: number;
  missed: number;
  precision: number;
  recall: number;
  f1: number;
  cost_usd: number;
  equivalent_cost_usd: number;
  cost_per_lead_usd: number | null;
  prefilter_recall: number;
  leads: { label: string; msg_id: number; author: string; note: string; found: boolean; stage: string; decision: string; fit: number | null; relevance: number | null }[];
  decoys: { label: string; msg_id: number; author: string; note: string; fooled: boolean; stage: string; decision: string; fit: number | null; relevance: number | null }[];
};
