import type { Overview } from "../types";
import { t, time, number } from "../i18n";

export function Metric({
  label,
  value,
  unit = "%",
  hint,
  level = false,
}: {
  label: string;
  value?: number;
  unit?: string;
  hint: string;
  level?: boolean;
}) {
  return (
    <article className={`metric ${level ? "pressure" : ""}`}>
      <div>
        <span>{t(label)}</span>
        <small title={hint}>{hint}</small>
      </div>
      <strong>
        {value === undefined ? "—" : number(value)}
        <em>{unit}</em>
      </strong>
      {unit === "%" && (
        <div
          className="metric-meter"
          role="meter"
          aria-label={t(label)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={value}
        >
          <i style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }} />
        </div>
      )}
    </article>
  );
}
export function RecentTrend({ overview }: { overview: Overview | null }) {
  const rows = [...(overview?.recent ?? [])].sort(
    (a, b) => Date.parse(a.finished_at) - Date.parse(b.finished_at),
  );
  if (rows.length < 2) return null;
  const first = Date.parse(rows[0].finished_at);
  const span = Math.max(
    1,
    Date.parse(rows[rows.length - 1].finished_at) - first,
  );
  const line = (key: "cpu_percent" | "memory_percent") =>
    rows
      .map(
        (row) =>
          `${((Date.parse(row.finished_at) - first) * 600) / span},${80 - row[key] * 0.7}`,
      )
      .join(" ");
  return (
    <div className="recent-trend">
      <div>
        <span>{t("recentLoad", { count: rows.length })}</span>
        <span>
          <b>CPU</b> / <em>RAM</em>
        </span>
      </div>
      <svg
        viewBox="0 0 600 90"
        preserveAspectRatio="none"
        role="img"
        aria-label={t("CPU and memory percentages across recent saved states")}
      >
        <title>
          {t("CPU and memory percentages across recent saved states")} · 0–100%
        </title>
        <path
          d="M0 10H600M0 45H600M0 80H600"
          stroke="#2b3b40"
          strokeDasharray="4 5"
        />
        <polyline
          points={line("memory_percent")}
          fill="none"
          stroke="#98b7f1"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
        <polyline
          points={line("cpu_percent")}
          fill="none"
          stroke="#76e2c3"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div>
        <span>{time(rows[0].finished_at)}</span>
        <span>0–100%</span>
        <span>{time(rows[rows.length - 1].finished_at)}</span>
      </div>
    </div>
  );
}
