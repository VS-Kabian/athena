export type Provider = { id: string; label: string; needs_key: boolean };

export type SourceEvent = {
  url: string; title: string; provider: string; source_type: string;
  round: number; providers: string[]; subquestion: string;
};

export type CoverageCell = {
  question: string; validated: number; relevant: number; best_relevance: number; score: number;
};
export type EntityCoverage = { entity: string; hits: number; covered: boolean };
export type Coverage = { cells: CoverageCell[]; entities: EntityCoverage[]; overall: number };

export type UrlHealth = { total: number; live: number; dead: number; unreachable: number };
export type EntailSummary = {
  engine: string; supported: number; refuted: number; nei: number; conflicts: number;
};

export type ResearchEvent =
  | { type: "round_start"; data: { round: number; questions: string[] } }
  | { type: "source"; data: SourceEvent }
  | { type: "progress"; data: { round: number; discovered: number } }
  | { type: "validated"; data: { count: number } }
  | { type: "fetching"; data: { count: number } }
  | { type: "quality"; data: { score: number; breakdown: QualityBreakdown; hallucination_risk: number; consensus?: number } }
  | { type: "reflect"; data: { round: number; action: string; reason: string } }
  | { type: "memory"; data: { related: { topic: string; similarity: number }[] } }
  | { type: "verify"; data: { contested: number } }
  | { type: "reading"; data: { round: number; count: number } }
  | { type: "coverage"; data: Coverage }
  | { type: "entail"; data: EntailSummary }
  | { type: "urlhealth"; data: UrlHealth }
  | { type: "report_delta"; data: { text: string } }
  | { type: "reasoning_delta"; data: { text: string } }
  | { type: "usage"; data: { total_tokens?: number; cost?: number } }
  | { type: "synthesizing"; data: Record<string, never> }
  | { type: "done"; data: { report_ready: boolean } }
  | { type: "cancelled"; data: Record<string, never> }
  | { type: "failed"; data: { message: string } };

export type LLMSpec = { provider: string; model: string; api_key?: string };
export type SearchSpec = { providers: string[]; mode: string; keys: Record<string, string> };

export type Citation = { n: number; url: string; title: string; excerpt: string; url_status?: string | null };
export type QualityBreakdown = {
  coverage: number; validation: number; grounding: number; relevance: number; depth: number;
  hallucination_risk?: number;
};

// The Trust Ledger (#2 entailment, #3 conflicts, #4 URL liveness) persisted on the report.
export type Trust = {
  engine?: string;
  supported?: number; refuted?: number; nei?: number; conflicts?: number;
  conflict_items?: string[];
  consensus?: number | null; single_source?: number;
  url_health?: UrlHealth;
  url_status?: Record<string, string>;
  coverage?: Coverage;
};
