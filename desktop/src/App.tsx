import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  loadOverview,
  refreshState,
  runInvestigation,
  loadStartupStatus,
  setStartupEnabled,
  loadStorageInfo,
  openHistoryFolder,
  clearHistory,
  loadHistoryPage,
} from "./api";
import type { StartupStatus } from "./api";
import type {
  Overview,
  Investigation,
  StorageInfo,
  HistoryPage,
} from "./types";
import { newestOverview } from "./overview";
import {
  t,
  useLocale,
  setLocale,
  languages,
  time,
  date,
  duration,
  size,
  number,
  readPreference,
  savePreference,
} from "./i18n";
import type { Locale } from "./i18n";
import { setNativeLocale } from "./api";
import { Pager } from "./components/Pager";
import { Result, ReportView } from "./components/InvestigationReport";
import { Metric, RecentTrend } from "./components/OverviewMetrics";

type Tab = "overview" | "report" | "history" | "settings";
const tabs: Array<[Tab, string]> = [
  ["overview", "Overview"],
  ["report", "Investigation"],
  ["history", "History"],
  ["settings", "Settings"],
];
const message = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

function Mark() {
  return (
    <svg className="brand-mark" viewBox="0 0 40 40" aria-hidden="true">
      <circle cx="17" cy="17" r="10" />
      <path d="m24 24 10 10M12 14q5-6 10 0" />
      <circle cx="17" cy="18" r="2" />
    </svg>
  );
}
export default function App() {
  const locale = useLocale();
  const [theme, setTheme] = useState(() => {
    const value = readPreference("theme");
    return value === "light" || value === "dark" ? value : "system";
  });
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (media.matches ? "light" : "dark") : theme;
    };
    apply();
    savePreference("theme", theme);
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => {
    void setNativeLocale(locale).catch((err) => setError(message(err)));
  }, [locale]);
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(
    null,
  );
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [startup, setStartup] = useState<StartupStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [monitorError, setMonitorError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{
    key: string;
    params?: Record<string, string | number>;
  }>({ key: "Reading local history…" });
  const [now, setNow] = useState(Date.now());
  const [height, setHeight] = useState(window.innerHeight);
  const [activity, setActivity] = useState<"states" | "processes">("states");
  const [history, setHistory] = useState<HistoryPage | null>(null);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [modal, setModal] = useState<"clear" | "error" | null>(null);
  const [errorPage, setErrorPage] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const operation = useRef(false);
  const clearing = useRef(false);
  const epoch = useRef(0);
  const pollBusy = useRef(false);
  const historyRequest = useRef(0);
  const [rowCount, setRowCount] = useState(3);
  const [activityCount, setActivityCount] = useState(3);
  const historyArea = useRef<HTMLDivElement>(null);
  const activityArea = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const measure = () => {
      if (historyArea.current)
        setRowCount(
          Math.max(
            1,
            Math.min(
              50,
              Math.floor((historyArea.current.clientHeight - 34) / 44),
            ),
          ),
        );
      if (activityArea.current)
        setActivityCount(
          Math.max(1, Math.floor(activityArea.current.clientHeight / 44)),
        );
    };
    const observer = new ResizeObserver(measure);
    if (historyArea.current) observer.observe(historyArea.current);
    if (activityArea.current) observer.observe(activityArea.current);
    measure();
    return () => observer.disconnect();
  }, [tab, height, locale]);

  const accept = useCallback((incoming: Overview) => {
    setOverview((current) => newestOverview(current, incoming));
    setStorage((current) =>
      current &&
      current.generation === incoming.storage.generation &&
      current.state_count > incoming.storage.state_count
        ? current
        : incoming.storage,
    );
  }, []);
  const poll = useCallback(async () => {
    if (pollBusy.current || clearing.current) return;
    pollBusy.current = true;
    const stamp = epoch.current;
    try {
      const status = await loadOverview();
      if (stamp !== epoch.current) return;
      if (status.overview) accept(status.overview);
      setMonitorError(status.error);
    } catch (err) {
      if (stamp === epoch.current) setMonitorError(message(err));
    } finally {
      pollBusy.current = false;
    }
  }, [accept]);
  useEffect(() => {
    void poll();
    const timer = window.setInterval(() => {
      setNow(Date.now());
      void poll();
    }, 1000);
    const resize = () => setHeight(window.innerHeight);
    window.addEventListener("resize", resize);
    const stamp = epoch.current;
    void loadStorageInfo()
      .then((value) => {
        if (stamp === epoch.current) {
          setStorage(value);
          setNotice({ key: "History is saved automatically on this PC." });
        }
      })
      .catch((err) => setError(message(err)));
    void loadStartupStatus()
      .then(setStartup)
      .catch((err) => setError(message(err)));
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("resize", resize);
    };
  }, [poll]);
  useEffect(() => {
    if (modal && dialog.current && !dialog.current.open)
      dialog.current.showModal();
    if (!modal && dialog.current?.open) dialog.current.close();
  }, [modal]);

  const readPage = useCallback(
    async (page: number, anchor: number | null = null) => {
      const request = ++historyRequest.current;
      const stamp = epoch.current;
      setHistoryBusy(true);
      try {
        const result = await loadHistoryPage(page, rowCount, anchor);
        if (request === historyRequest.current && stamp === epoch.current)
          setHistory(result);
      } catch (err) {
        if (stamp === epoch.current) setError(message(err));
      } finally {
        if (request === historyRequest.current) setHistoryBusy(false);
      }
    },
    [rowCount],
  );
  useEffect(() => {
    if (tab === "history") void readPage(0);
  }, [tab, readPage, storage?.generation]);

  const perform = async (name: string, action: () => Promise<void>) => {
    if (operation.current) return;
    operation.current = true;
    setBusy(name);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(message(err));
    } finally {
      operation.current = false;
      setBusy(null);
    }
  };
  const refresh = () =>
    perform("refresh", async () => {
      const fresh = await refreshState();
      accept(fresh);
      setMonitorError(null);
      setNotice({
        key: "stateSaved",
        params: {
          id: fresh.current.state_id,
          time: time(fresh.current.finished_at),
        },
      });
      if (tab === "history") void readPage(0);
    });
  const run = (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    void perform("investigate", async () => {
      const result = await runInvestigation(question.trim());
      setInvestigation(result);
      setNotice({ key: "caseDone", params: { id: result.current.state_id } });
    });
  };
  const erase = () =>
    perform("clear", async () => {
      clearing.current = true;
      epoch.current++;
      historyRequest.current++;
      try {
        const result = await clearHistory();
        setOverview(null);
        setInvestigation(null);
        setStorage(result.storage);
        setHistory(null);
        setMonitorError(null);
        setHistoryBusy(false);
        setModal(null);
        setNotice({
          key: "statesDeleted",
          params: { count: result.deleted_count },
        });
      } finally {
        clearing.current = false;
      }
    });
  const folder = () =>
    perform("folder", async () => {
      setStorage(await openHistoryFolder());
      setNotice({ key: "Opened the folder containing sherlock.db." });
    });
  const snapshot = overview?.current;
  const age = snapshot
    ? Math.max(0, (now - new Date(snapshot.finished_at).getTime()) / 1000)
    : 0;
  const issue = error || monitorError || startup?.error;
  const stale = !!snapshot && age > 30;
  const ready = overview?.history.status === "enough_data";
  const errorText = issue ?? t("No errors reported.");
  const errorParts = errorText.match(/[\s\S]{1,360}/g) ?? [errorText];
  const storageControls = (
    <div className="storage-controls">
      <input
        dir="ltr"
        aria-label={t("History database path")}
        readOnly
        value={storage?.database_path ?? t("Loading database path…")}
        title={storage?.database_path}
      />
      <button onClick={() => void folder()} disabled={!!busy || !storage}>
        {busy === "folder" ? t("Opening…") : t("Open folder")}
      </button>
      <button
        className="danger-quiet"
        onClick={() => setModal("clear")}
        disabled={!!busy || !storage?.state_count}
      >
        {t("Clear all states")}
      </button>
    </div>
  );

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <Mark />
          <div>
            <strong>
              SherlockPC <small>v0.1</small>
            </strong>
            <span>{t("Observe & investigate")}</span>
          </div>
        </div>
        <div className="header-actions">
          <label className="language-control">
            <span aria-hidden="true">◎</span>
            <select
              aria-label={t("Language")}
              value={locale}
              onChange={(event) => setLocale(event.target.value as Locale)}
            >
              {Object.entries(languages).map(([id, name]) => (
                <option
                  key={id}
                  value={id}
                  lang={id}
                  dir={id === "ar" ? "rtl" : "ltr"}
                >
                  {name}
                </option>
              ))}
            </select>
          </label>
          <span className={`status ${stale || monitorError ? "warning" : ""}`}>
            <i />
            {stale
              ? t("Collection delayed")
              : monitorError
                ? t("Collector issue")
                : !snapshot
                  ? t("Starting collector…")
                  : t("Collecting · every 10 sec")}
          </span>
          <button
            onClick={() => void refresh()}
            disabled={!!busy}
            className="refresh-button"
          >
            {busy === "refresh" ? t("Capturing…") : t("↻ Refresh state")}
          </button>
        </div>
      </header>
      <section className="metrics" aria-label={t("Latest system state")}>
        <Metric
          label="CPU"
          value={snapshot?.system.cpu_percent}
          hint={t("Processor load")}
          level={(snapshot?.system.cpu_percent ?? 0) >= 90}
        />
        <Metric
          label={t("Memory")}
          value={snapshot?.system.memory_percent}
          hint={
            snapshot
              ? t("usedMemory", {
                  value: number(snapshot.system.memory_used_gib, 1),
                })
              : t("Waiting for sample")
          }
          level={(snapshot?.system.memory_percent ?? 0) >= 90}
        />
        <Metric
          label={t("Swap")}
          value={snapshot?.system.swap_percent}
          hint={t("Swap usage")}
          level={(snapshot?.system.swap_percent ?? 0) >= 50}
        />
        <Metric
          label={t("Processes")}
          value={snapshot?.processes.count}
          unit=""
          hint={
            snapshot
              ? t("stateTime", {
                  id: snapshot.state_id,
                  time: time(snapshot.finished_at),
                })
              : t("Waiting for sample")
          }
        />
      </section>
      <nav className="tabs" aria-label={t("Main views")}>
        {tabs.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={tab === id ? "active" : ""}
            aria-current={tab === id ? "page" : undefined}
          >
            {t(label)}
            {id === "history" && <span>{storage?.state_count ?? 0}</span>}
          </button>
        ))}
        <span className="nav-note">
          {snapshot
            ? t("sampleAge", { age: duration(age) })
            : t("Waiting for next sample")}
        </span>
      </nav>
      <div className="workspace">
        {tab === "overview" && (
          <div className="overview-grid">
            <section className="panel question-panel">
              <div className="panel-title">
                <h1>{t("Investigate this PC")}</h1>
                <span className="badge">{t("Local only")}</span>
              </div>
              <p className="scope-note">
                {t(
                  "CPU, RAM and swap check. The question labels the check; free-form answers are not available yet.",
                )}
              </p>
              <form onSubmit={run}>
                <input
                  aria-label={t("Diagnostic question")}
                  placeholder={t("Describe a slowdown…")}
                  maxLength={500}
                  dir="auto"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  disabled={!!busy}
                />
                <button
                  className="primary"
                  disabled={!!busy || !question.trim()}
                >
                  {busy === "investigate" ? t("Checking…") : t("Investigate →")}
                </button>
              </form>
              <div className="quick-actions">
                <button onClick={() => setQuestion(t("Is CPU load unusual?"))}>
                  {t("Check CPU")}
                </button>
                <button
                  onClick={() => setQuestion(t("Is memory pressure high?"))}
                >
                  {t("Check memory")}
                </button>
                {investigation && (
                  <button onClick={() => setTab("report")}>
                    {t("View full report →")}
                  </button>
                )}
              </div>
              <Result investigation={investigation} />
              <RecentTrend overview={overview} />
            </section>
            <section className="panel activity-panel">
              <div className="panel-title">
                <h2>{t("Live activity")}</h2>
                <span className={`badge ${ready ? "mint" : ""}`}>
                  {ready ? t("History ready") : t("Building history")}
                </span>
              </div>
              <div className="history-summary">
                <div>
                  <strong>{overview?.history.sample_count ?? 0}</strong>
                  <span>{t("baseline samples")}</span>
                </div>
                <div>
                  <strong>
                    {duration(overview?.history.span_seconds ?? 0)}
                  </strong>
                  <span>{t("span, including gaps")}</span>
                </div>
              </div>
              <div className="readiness">
                <div>
                  <span>{t("Baseline readiness")}</span>
                  <strong>
                    {number(
                      Math.min(
                        100,
                        Math.floor(
                          100 *
                            Math.min(
                              (overview?.history.sample_count ?? 0) /
                                Math.max(
                                  1,
                                  overview?.history.min_samples ?? 30,
                                ),
                              (overview?.history.span_seconds ?? 0) /
                                Math.max(
                                  1,
                                  overview?.history.min_span_seconds ?? 300,
                                ),
                            ),
                        ),
                      ),
                    )}
                    %
                  </strong>
                </div>
                <progress
                  aria-label={t("Baseline readiness")}
                  max={1}
                  value={Math.min(
                    1,
                    (overview?.history.sample_count ?? 0) /
                      Math.max(1, overview?.history.min_samples ?? 30),
                    (overview?.history.span_seconds ?? 0) /
                      Math.max(1, overview?.history.min_span_seconds ?? 300),
                  )}
                />
                <small>
                  {t("readinessCounts", {
                    samples: overview?.history.sample_count ?? 0,
                    minSamples: overview?.history.min_samples ?? 30,
                    span: duration(overview?.history.span_seconds ?? 0),
                    minSpan: duration(
                      overview?.history.min_span_seconds ?? 300,
                    ),
                  })}
                </small>
              </div>
              <div className="segmented">
                <button
                  className={activity === "states" ? "selected" : ""}
                  onClick={() => setActivity("states")}
                >
                  {t("Recent states")}
                </button>
                <button
                  className={activity === "processes" ? "selected" : ""}
                  onClick={() => setActivity("processes")}
                >
                  {t("Top memory")}
                </button>
              </div>
              <div className="activity-list" ref={activityArea}>
                {activity === "states"
                  ? (overview?.recent ?? [])
                      .slice(0, activityCount)
                      .map((item) => (
                        <div className="activity-row" key={item.state_id}>
                          <strong>
                            <bdi dir="ltr">#{item.state_id}</bdi>
                            <small>
                              <bdi dir="ltr">{time(item.finished_at)}</bdi>
                            </small>
                          </strong>
                          <span dir="ltr">CPU {number(item.cpu_percent)}%</span>
                          <span dir="ltr">
                            RAM {number(item.memory_percent)}%
                          </span>
                        </div>
                      ))
                  : (snapshot?.processes.top_memory ?? [])
                      .slice(0, activityCount)
                      .map((item) => (
                        <div className="activity-row" key={item.pid}>
                          <strong title={item.name}>
                            {item.name}
                            <small>PID {item.pid}</small>
                          </strong>
                          <span>
                            {item.memory_rss_gib == null
                              ? "—"
                              : number(item.memory_rss_gib, 2)}{" "}
                            GiB
                          </span>
                        </div>
                      ))}
                {!snapshot && (
                  <p className="muted">
                    {t("The next background sample will appear here.")}
                  </p>
                )}
              </div>
              <button
                className="text-button"
                onClick={() =>
                  setTab(activity === "states" ? "history" : "settings")
                }
              >
                {activity === "states"
                  ? t("Browse saved history →")
                  : t("Manage background collection →")}
              </button>
            </section>
          </div>
        )}
        {tab === "report" && (
          <ReportView
            key={investigation?.current.state_id ?? "empty"}
            investigation={investigation}
          />
        )}
        {tab === "history" && (
          <section className="panel history-panel">
            <div className="panel-title">
              <h1>
                {t("Saved states")}
                <span className="muted">{storage?.state_count ?? 0}</span>
              </h1>
              <button
                onClick={() => void readPage(0)}
                disabled={historyBusy || !!busy}
              >
                {t("Reload list")}
              </button>
            </div>
            {storageControls}
            <div className="table-wrap" ref={historyArea}>
              <table>
                <thead>
                  <tr>
                    <th>{t("State")}</th>
                    <th>{t("Captured")}</th>
                    <th>CPU</th>
                    <th>RAM</th>
                    <th>{t("Swap")}</th>
                    <th>{t("Processes")}</th>
                  </tr>
                </thead>
                <tbody>
                  {history?.rows.map((item) => (
                    <tr key={item.state_id}>
                      <td>
                        <bdi dir="ltr">#{item.state_id}</bdi>
                      </td>
                      <td>
                        {date(item.finished_at)} · {time(item.finished_at)}
                      </td>
                      <td>{number(item.cpu_percent)}%</td>
                      <td>{number(item.memory_percent)}%</td>
                      <td>{number(item.swap_percent)}%</td>
                      <td>{item.process_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!history?.rows.length && (
                <p className="table-empty">
                  {historyBusy
                    ? t("Loading saved states…")
                    : t(
                        "No saved states. Background collection will add new samples.",
                      )}
                </p>
              )}
            </div>
            <div className="history-bottom">
              <span className="muted">
                {t("historyCount", {
                  count: history?.total ?? 0,
                  size: storage ? size(storage.size_bytes) : "—",
                })}
              </span>
              <Pager
                page={history?.page ?? 0}
                pages={Math.ceil((history?.total ?? 0) / rowCount)}
                onChange={(page) => void readPage(page, history?.anchor_id)}
                disabled={historyBusy || !!busy}
              />
            </div>
          </section>
        )}
        {tab === "settings" && (
          <section className="panel settings-panel">
            <div className="panel-title">
              <h1>{t("Settings & storage")}</h1>
              <span className="badge">{t("This PC only")}</span>
            </div>
            <div className="settings-grid">
              <div>
                <h2>{t("Background collection")}</h2>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={startup?.enabled ?? false}
                    disabled={!startup?.supported || !!busy}
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      void perform("startup", async () => {
                        setStartup(await setStartupEnabled(enabled));
                        setNotice({
                          key: enabled
                            ? "Windows autostart enabled."
                            : "Windows autostart disabled.",
                        });
                      });
                    }}
                  />
                  <span>
                    {t("Start in background when I sign in to Windows")}
                  </span>
                </label>
                <p>{t("Tray help")}</p>
                {startup && !startup.supported && (
                  <small>
                    {t(
                      "Autostart is available in the installed Windows release.",
                    )}
                  </small>
                )}
              </div>
              <div>
                <h2>{t("Your history")}</h2>
                <p>{t("Storage help")}</p>
                <p>
                  <strong>
                    {t("statesCount", { count: storage?.state_count ?? 0 })}
                  </strong>{" "}
                  · {storage ? size(storage.size_bytes) : "—"}
                </p>
                <small>
                  {t(
                    "Clearing history removes saved states. Automatic collection then starts a new history.",
                  )}
                </small>
              </div>
            </div>
            <div className="preferences">
              <label>
                {t("Appearance")}
                <select
                  value={theme}
                  onChange={(event) => setTheme(event.target.value)}
                >
                  <option value="system">{t("System")}</option>
                  <option value="dark">{t("Dark")}</option>
                  <option value="light">{t("Light")}</option>
                </select>
              </label>
              <small>{t("Preferences are saved on this PC.")}</small>
            </div>
            {storageControls}
          </section>
        )}
      </div>
      <footer>
        <span role="status" title={t(notice.key, notice.params)}>
          {t(notice.key, notice.params)}
        </span>
        <div className="footer-actions">
          {issue && (
            <button
              className="error-link"
              onClick={() => {
                setErrorPage(0);
                setModal("error");
              }}
            >
              {t("View error ↗")}
            </button>
          )}
          <button
            className="text-button"
            onClick={() => void folder()}
            disabled={!!busy || !storage}
          >
            {t("History location ↗")}
          </button>
        </div>
      </footer>
      <dialog
        aria-label={
          modal === "clear" ? t("CLEAR LOCAL HISTORY") : t("Operation details")
        }
        ref={dialog}
        onCancel={(event) => {
          event.preventDefault();
          if (!busy) setModal(null);
        }}
      >
        <div className="dialog-content">
          {modal === "clear" ? (
            <>
              <span className="section-tag">{t("CLEAR LOCAL HISTORY")}</span>
              <h2>
                {t("deleteConfirm", { count: storage?.state_count ?? 0 })}
              </h2>
              <p>
                {t(
                  "Saved system and process measurements belonging to these states will be removed. This cannot be undone.",
                )}
              </p>
              <p className="muted">
                {t("Background collection will continue with a new history.")}
              </p>
              {error && <p className="error-link">{error.slice(0, 250)}</p>}
              <div className="dialog-actions">
                <button
                  autoFocus
                  onClick={() => setModal(null)}
                  disabled={!!busy}
                >
                  {t("Cancel")}
                </button>
                <button
                  className="danger"
                  onClick={() => void erase()}
                  disabled={!!busy}
                >
                  {busy === "clear" ? t("Deleting…") : t("Delete all states")}
                </button>
              </div>
            </>
          ) : (
            <>
              <h2>{t("Operation details")}</h2>
              <p>
                {t("An operation failed. Check the details and try again.")}
              </p>
              <small>{t("Raw technical details")}</small>
              <p className="error-detail" dir="auto">
                {errorParts[Math.min(errorPage, errorParts.length - 1)]}
              </p>
              <Pager
                page={errorPage}
                pages={errorParts.length}
                onChange={setErrorPage}
              />
              <button onClick={() => setModal(null)}>{t("Close")}</button>
            </>
          )}
        </div>
      </dialog>
    </main>
  );
}
