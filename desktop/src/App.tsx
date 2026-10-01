import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { loadOverview, runInvestigation } from "./api";
import type { Investigation, Overview, Snapshot, Verdict } from "./types";

const DEFAULT_QUESTION = "Почему компьютер начал тормозить?";

function metricLevel(value: number, elevated: number, high: number) {
  if (value >= high) return "high";
  if (value >= elevated) return "elevated";
  return "normal";
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function MetricCard({ label, value, suffix, level }: {
  label: string;
  value: string | number;
  suffix?: string;
  level: "normal" | "elevated" | "high" | "neutral";
}) {
  return (
    <article className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-row">
        <strong>{value}{suffix}</strong>
        <span className={`status-dot ${level}`}>{level}</span>
      </div>
    </article>
  );
}

function SystemHealth({ snapshot }: { snapshot: Snapshot }) {
  const { system, processes } = snapshot;
  return (
    <section className="panel health-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">LIVE SNAPSHOT</span>
          <h2>System Health</h2>
        </div>
        <span className="local-badge">● LOCAL</span>
      </div>

      <div className="metric-grid">
        <MetricCard label="CPU" value={system.cpu_percent.toFixed(1)} suffix="%" level={metricLevel(system.cpu_percent, 70, 90)} />
        <MetricCard label="RAM" value={system.memory_percent.toFixed(1)} suffix="%" level={metricLevel(system.memory_percent, 75, 90)} />
        <MetricCard label="Swap" value={system.swap_percent.toFixed(1)} suffix="%" level={metricLevel(system.swap_percent, 20, 50)} />
        <MetricCard label="Processes" value={processes.count} level="neutral" />
      </div>

      <div className="memory-line">
        <span>{system.memory_used_gib.toFixed(2)} GiB used</span>
        <span>{system.memory_available_gib.toFixed(2)} GiB available</span>
      </div>
      <p className="microcopy">Status labels are UI thresholds, not a diagnosis. Disk/GPU health are not collected in this alpha.</p>
    </section>
  );
}

function verdictFor(investigation: Investigation, hypothesisId: string): Verdict | undefined {
  return investigation.report.reasoning?.verdicts.find((item) => item.hypothesis_id === hypothesisId);
}

function InvestigationPanel({ investigation }: { investigation: Investigation | null }) {
  if (!investigation) {
    return (
      <section className="panel investigation-panel empty-state">
        <div className="empty-orbit">S</div>
        <h2>No investigation yet</h2>
        <p>Ask a diagnostic question. Sherlock will capture a real state, compare it with stored history and show the evidence trail.</p>
      </section>
    );
  }

  const { report } = investigation;
  const sampleCount = report.anomaly_report?.evidence_report.baseline.sample_count ?? 0;
  const span = report.anomaly_report?.evidence_report.baseline.span_seconds ?? 0;

  return (
    <section className="panel investigation-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">CASE #{investigation.current.state_id}</span>
          <h2>Investigation</h2>
        </div>
        <span className={`case-status ${report.status.toLowerCase()}`}>{report.status.replaceAll("_", " ")}</span>
      </div>

      <div className="question-card">
        <span>Question</span>
        <strong>{investigation.question}</strong>
      </div>

      <div className="conclusion-card">
        <span>Conclusion</span>
        <p>{report.conclusion}</p>
        <small>Baseline: {sampleCount} samples · {span.toFixed(0)} s</small>
      </div>

      {report.reasoning && report.reasoning.hypotheses.length > 0 && (
        <div className="section-block">
          <h3>Hypotheses</h3>
          <div className="hypothesis-list">
            {report.reasoning.hypotheses.map((hypothesis) => {
              const verdict = verdictFor(investigation, hypothesis.hypothesis_id);
              return (
                <article className="hypothesis" key={hypothesis.hypothesis_id}>
                  <div>
                    <strong>{hypothesis.statement}</strong>
                    <span>{hypothesis.evidence_ids.join(" · ") || "No evidence reference"}</span>
                  </div>
                  <em>{verdict?.status.replaceAll("_", " ") || "UNVERIFIED"}</em>
                </article>
              );
            })}
          </div>
        </div>
      )}

      <div className="section-block">
        <h3>Investigation trace</h3>
        <div className="trace-list">
          {report.trace.map((event, index) => (
            <div className="trace-row" key={`${event.stage}-${index}`}>
              <span className="trace-check">✓</span>
              <div>
                <strong>{event.stage.replaceAll("_", " ")}</strong>
                <p>{event.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {report.findings.length > 0 && (
        <div className="section-block">
          <h3>Evidence-backed findings</h3>
          {report.findings.map((finding) => (
            <div className="finding" key={finding.evidence_ids.join("-")}>
              <p>{finding.statement}</p>
              <code>{finding.evidence_ids.join(", ")}</code>
            </div>
          ))}
        </div>
      )}

      {report.error && <div className="error-box">{report.error}</div>}
      <details className="limitations">
        <summary>Limitations</summary>
        <ul>{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </section>
  );
}

export default function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [loading, setLoading] = useState(true);
  const [investigating, setInvestigating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOverview(await loadOverview());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    setInvestigating(true);
    setError(null);
    try {
      const result = await runInvestigation(question);
      setInvestigation(result);
      setOverview((current) => current ? { ...current, current: result.current } : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setInvestigating(false);
    }
  };

  const snapshot = investigation?.current ?? overview?.current ?? null;
  const recent = useMemo(() => overview?.recent ?? [], [overview]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">S</div>
          <div>
            <strong>SherlockPC</strong>
            <span>Evidence-driven desktop investigator</span>
          </div>
        </div>
        <button className="ghost-button" onClick={() => void refresh()} disabled={loading}>
          {loading ? "Capturing…" : "Refresh snapshot"}
        </button>
      </header>

      {error && <div className="global-error">Backend error: {error}</div>}

      <section className="hero-grid">
        <div className="ask-panel panel">
          <span className="eyebrow">DIAGNOSE MODE · ALPHA</span>
          <h1>Ask Sherlock</h1>
          <p>Describe a slowdown. This build uses stored system evidence, not an LLM-generated guess.</p>
          <form onSubmit={run}>
            <textarea value={question} maxLength={500} onChange={(event) => setQuestion(event.target.value)} />
            <div className="ask-actions">
              <span>CPU · RAM · Swap · Processes</span>
              <button className="primary-button" disabled={investigating || !question.trim()}>
                {investigating ? "Investigating…" : "Investigate"}
              </button>
            </div>
          </form>
        </div>
        {snapshot ? <SystemHealth snapshot={snapshot} /> : <section className="panel skeleton-panel">Capturing local system state…</section>}
      </section>

      <section className="content-grid">
        <InvestigationPanel investigation={investigation} />

        <aside className="right-column">
          <section className="panel process-panel">
            <div className="panel-heading"><div><span className="eyebrow">CURRENT STATE</span><h2>Top memory</h2></div></div>
            {snapshot?.processes.top_memory.map((process) => (
              <div className="process-row" key={`${process.pid}-${process.name}`}>
                <div><strong>{process.name}</strong><span>PID {process.pid}</span></div>
                <em>{process.memory_rss_gib === null ? "N/A" : `${process.memory_rss_gib.toFixed(2)} GiB`}</em>
              </div>
            )) || <p className="muted">No snapshot yet.</p>}
          </section>

          <section className="panel recent-panel">
            <div className="panel-heading"><div><span className="eyebrow">LOCAL HISTORY</span><h2>Recent states</h2></div></div>
            {recent.length === 0 && <p className="muted">No stored states yet.</p>}
            {recent.map((state) => (
              <div className="recent-row" key={state.state_id}>
                <div><strong>State #{state.state_id}</strong><span>{formatTime(state.finished_at)}</span></div>
                <div className="recent-metrics"><span>CPU {state.cpu_percent.toFixed(0)}%</span><span>RAM {state.memory_percent.toFixed(0)}%</span></div>
              </div>
            ))}
          </section>
        </aside>
      </section>

      <footer>
        <span>Local-first · bounded investigation · no unrestricted shell access</span>
        <span>Desktop Alpha 0.1</span>
      </footer>
    </main>
  );
}
