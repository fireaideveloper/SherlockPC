export type Snapshot = {
  state_id: number;
  started_at: string;
  finished_at: string;
  system: {
    timestamp: string;
    cpu_percent: number;
    memory_percent: number;
    memory_used_gib: number;
    memory_available_gib: number;
    swap_percent: number;
  };
  processes: {
    count: number;
    skipped_count: number;
    top_memory: Array<{
      pid: number;
      name: string;
      status: string | null;
      memory_rss_gib: number | null;
      cpu_seconds: number | null;
    }>;
  };
};

export type RecentState = {
  state_id: number;
  started_at: string;
  finished_at: string;
  cpu_percent: number;
  memory_percent: number;
  process_count: number;
  skipped_count: number;
};

export type Overview = {
  current: Snapshot;
  recent: RecentState[];
  capabilities: Record<string, boolean>;
};

export type TraceEvent = {
  stage: string;
  detail: string;
};

export type Finding = {
  statement: string;
  evidence_ids: string[];
};

export type Hypothesis = {
  hypothesis_id: string;
  kind: string;
  statement: string;
  evidence_ids: string[];
};

export type Verdict = {
  hypothesis_id: string;
  status: "SUPPORTED_SIGNAL" | "INSUFFICIENT_EVIDENCE" | "REJECTED";
  reason: string;
  evidence_ids: string[];
  cause_confirmed: boolean;
};

export type Investigation = {
  question: string;
  mode: "diagnose";
  current: Snapshot;
  note: string;
  report: {
    status: "ANOMALIES_FOUND" | "NO_ANOMALY_FOUND" | "INSUFFICIENT_EVIDENCE" | "DATA_UNAVAILABLE";
    conclusion: string;
    findings: Finding[];
    trace: TraceEvent[];
    limitations: string[];
    error: string | null;
    reasoning: null | {
      summary: string;
      hypotheses: Hypothesis[];
      verdicts: Verdict[];
    };
    anomaly_report: null | {
      evidence_report: {
        baseline: {
          sample_count: number;
          span_seconds: number;
          reasons: string[];
        };
      };
    };
  };
};
