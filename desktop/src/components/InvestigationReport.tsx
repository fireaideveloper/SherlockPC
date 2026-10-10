import { useState } from "react";
import type { Investigation } from "../types";
import { t, time, duration } from "../i18n";
import { reportText } from "../reportText";
import { Pager } from "./Pager";

type ReportTab = "summary" | "findings" | "trace" | "limits";
const labels: Record<Investigation["report"]["status"], string> = {
  ANOMALIES_FOUND: "Signals found",
  NO_ANOMALY_FOUND: "No deviations found",
  INSUFFICIENT_EVIDENCE: "Building history",
  DATA_UNAVAILABLE: "Data unavailable",
};

export function Result({
  investigation,
}: {
  investigation: Investigation | null;
}) {
  if (!investigation)
    return (
      <div className="result-empty">
        <span className="section-tag">{t("READY TO CHECK")}</span>
        <h2>{t("Your next investigation")}</h2>
        <p>
          {t(
            "Capture this PC’s current state and compare CPU, RAM and swap with its saved history.",
          )}
        </p>
      </div>
    );
  return (
    <div
      className={`result ${investigation.report.status === "ANOMALIES_FOUND" ? "signal" : ""}`}
    >
      <div className="row">
        <span className="section-tag">
          {t("case", { id: investigation.current.state_id })}
        </span>
        <span className="badge">{t(labels[investigation.report.status])}</span>
      </div>
      <h2>
        {investigation.report.status === "INSUFFICIENT_EVIDENCE"
          ? t("More history is needed")
          : t("Investigation result")}
      </h2>
      <p>{reportText(investigation.report.conclusion)}</p>
      <small>
        {t("checked", { time: time(investigation.current.finished_at) })}
      </small>
    </div>
  );
}
export function ReportView({
  investigation,
}: {
  investigation: Investigation | null;
}) {
  const [section, setSection] = useState<ReportTab>("summary");
  const [page, setPage] = useState(0);
  if (!investigation)
    return (
      <section className="panel">
        <Result investigation={null} />
      </section>
    );
  const report = investigation.report;
  const findings = [
    ...report.findings.map((item) => ({
      title: t("Measured deviation"),
      text: item.statement,
      detail: "",
      sources: item.evidence_ids,
    })),
    ...(report.reasoning?.hypotheses ?? []).map((item) => {
      const verdict = report.reasoning?.verdicts.find(
        (v) => v.hypothesis_id === item.hypothesis_id,
      );
      return {
        title: verdict?.status ?? t("Hypothesis"),
        text: item.statement,
        detail: verdict?.reason ?? "",
        sources: item.evidence_ids,
      };
    }),
  ];
  const entries =
    section === "trace"
      ? report.trace.map((item) => ({
          title: item.stage,
          text: item.detail,
          detail: "",
          sources: [] as string[],
        }))
      : section === "limits"
        ? report.limitations.map((item) => ({
            title: t("Interpretation limit"),
            text: item,
            detail: "",
            sources: [] as string[],
          }))
        : findings;
  const safePage = Math.min(page, Math.max(0, entries.length - 1));
  const item = entries[safePage];
  const baseline = report.anomaly_report?.evidence_report.baseline;
  return (
    <section className="panel report-panel">
      <div className="panel-title">
        <h2>{t("reportTitle", { id: investigation.current.state_id })}</h2>
        <span className="muted">{time(investigation.current.finished_at)}</span>
      </div>
      <div className="report-layout">
        <div
          className="report-sections"
          role="tablist"
          aria-label={t("Report sections")}
        >
          {(
            [
              ["summary", t("Summary")],
              ["findings", t("Findings")],
              ["trace", t("Trace")],
              ["limits", t("Limits")],
            ] as Array<[ReportTab, string]>
          ).map(([id, label]) => (
            <button
              role="tab"
              aria-selected={section === id}
              className={section === id ? "selected" : ""}
              onClick={() => {
                setSection(id);
                setPage(0);
              }}
              key={id}
            >
              {t(label)}
            </button>
          ))}
        </div>
        <div className="report-content" role="tabpanel" tabIndex={0}>
          {section === "summary" ? (
            <>
              <Result investigation={investigation} />
              <label className="field-label">
                {t("Question")}
                <input
                  readOnly
                  dir="auto"
                  value={investigation.question}
                  aria-label={t("Question used for this report")}
                />
              </label>
              <p className="muted">
                {baseline
                  ? t("baselineInfo", {
                      count: baseline.sample_count,
                      span: duration(baseline.span_seconds),
                    })
                  : t("No baseline available")}
              </p>
            </>
          ) : (
            <>
              <div className="detail-card">
                <span className="section-tag">
                  {reportText(item?.title ?? "No findings")}
                </span>
                <h2>
                  {t("entryCount", {
                    current: entries.length ? safePage + 1 : 0,
                    total: entries.length,
                  })}
                </h2>
                <p>
                  {reportText(
                    item?.text ??
                      "No supported deviations or hypotheses were found under these rules.",
                  )}
                </p>
                {item?.detail && (
                  <p className="muted">{reportText(item.detail)}</p>
                )}
                {!!item?.sources.length && (
                  <label className="field-label">
                    {t("Evidence references")} · {item.sources.length}
                    <input
                      readOnly
                      dir="ltr"
                      value={item.sources.join(" · ")}
                      aria-label={t("Evidence references")}
                    />
                  </label>
                )}
              </div>
              <Pager
                page={safePage}
                pages={entries.length}
                onChange={setPage}
              />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
