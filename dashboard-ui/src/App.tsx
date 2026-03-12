import { useEffect, useRef, useState } from "react";

type Dictionary = Record<string, unknown>;

type QueueRow = {
  issue_id: string;
  repo: string;
  title: string;
  state: string;
  explanation_summary?: string;
  failure_summary?: string;
  recommended_action?: string;
  pr_badge?: string;
  updated_at?: string;
  view_memberships?: string[];
};

type QueuePayload = {
  rows: QueueRow[];
  views: Array<{ id: string; label: string; count: number }>;
  summary: Record<string, number>;
};

type OverviewPayload = {
  rows: Array<Record<string, unknown>>;
  logs?: { lines?: string[]; files?: string[] };
  activity?: ActivityRow[];
  scoreboard?: Record<string, number>;
  chart_series?: {
    reliability?: Array<Record<string, unknown>>;
  };
};

type ActivityRow = {
  id: string;
  kind: string;
  timestamp?: string;
  summary?: string;
  message?: string;
  repo?: string;
  signal?: string;
  subsystem?: string;
  issue_id?: string;
};

type IssueDetailPayload = {
  found?: boolean;
  repo?: {
    name?: string;
    path?: string;
    trust?: Dictionary;
    policy?: Dictionary;
  };
  issue?: Dictionary;
  attempts?: Dictionary[];
  activity?: ActivityRow[];
};

type BootstrapPayload = {
  notice?: string;
  authMode?: string;
  authTokenEnv?: string;
  refreshMs?: number;
  generatedAt?: string;
};

const EMPTY_QUEUE: QueuePayload = { rows: [], views: [], summary: {} };
const EMPTY_OVERVIEW: OverviewPayload = { rows: [], logs: { lines: [], files: [] }, activity: [], scoreboard: {}, chart_series: { reliability: [] } };

const DETAIL_TABS = [
  { id: "detail", label: "Detail" },
  { id: "activity", label: "Activity" },
  { id: "logs", label: "Logs" },
] as const;

const HEALTH_TABS = [
  { id: "health", label: "Health" },
  { id: "actions", label: "Actions" },
] as const;

function formatCount(value: unknown): string {
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric)) {
    return "0";
  }
  return numeric.toLocaleString();
}

function formatPercent(value: unknown): string {
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric)) {
    return "0%";
  }
  return `${Math.round(numeric * 100)}%`;
}

function stateTone(state: string): string {
  const normalized = String(state || "").toLowerCase();
  if (["running", "claimed", "verify_pending"].includes(normalized)) {
    return "running";
  }
  if (["blocked", "failed"].includes(normalized)) {
    return "blocked";
  }
  if (["pr_open", "pr_pending_approval"].includes(normalized)) {
    return "success";
  }
  return "idle";
}

function activityTone(signal: string | undefined): string {
  if (signal === "failure") {
    return "blocked";
  }
  if (signal === "running") {
    return "running";
  }
  if (signal === "ok") {
    return "success";
  }
  return "idle";
}

function asRecord(value: unknown): Dictionary {
  return value && typeof value === "object" ? (value as Dictionary) : {};
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function App({ bootstrap }: { bootstrap: BootstrapPayload }) {
  const refreshMs = Number(bootstrap.refreshMs || 5000);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const [queue, setQueue] = useState<QueuePayload>(EMPTY_QUEUE);
  const [overview, setOverview] = useState<OverviewPayload>(EMPTY_OVERVIEW);
  const [detail, setDetail] = useState<IssueDetailPayload | null>(null);
  const [selectedIssueId, setSelectedIssueId] = useState("");
  const [selectedRepo, setSelectedRepo] = useState("");
  const [selectedView, setSelectedView] = useState("all");
  const [search, setSearch] = useState("");
  const [mobileTab, setMobileTab] = useState<"queue" | "detail" | "health">("queue");
  const [detailTab, setDetailTab] = useState<(typeof DETAIL_TABS)[number]["id"]>("detail");
  const [healthTab, setHealthTab] = useState<(typeof HEALTH_TABS)[number]["id"]>("health");
  const [notice, setNotice] = useState(bootstrap.notice || "");
  const [authToken, setAuthToken] = useState("");
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const stored = globalThis.localStorage?.getItem("flow-healer-theme");
    return stored === "light" ? "light" : "dark";
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const searchText = search.trim().toLowerCase();
  const filteredRows = (queue.rows || []).filter((row) => {
    const inView = selectedView === "all" || (row.view_memberships || []).includes(selectedView);
    if (!inView) {
      return false;
    }
    if (!searchText) {
      return true;
    }
    const haystack = [row.title, row.repo, row.issue_id, row.explanation_summary, row.failure_summary]
      .join(" ")
      .toLowerCase();
    return haystack.includes(searchText);
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("flow-healer-theme", theme);
  }, [theme]);

  useEffect(() => {
    let cancelled = false;

    async function loadOverview() {
      try {
        const [nextQueue, nextOverview] = await Promise.all([
          fetchJson<QueuePayload>("/api/queue"),
          fetchJson<OverviewPayload>("/api/overview"),
        ]);
        if (cancelled) {
          return;
        }
        setQueue(nextQueue);
        setOverview(nextOverview);
        setError("");
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load dashboard data.");
        }
      }
    }

    void loadOverview();
    const timer = window.setInterval(() => void loadOverview(), refreshMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [refreshMs]);

  useEffect(() => {
    if (!filteredRows.length) {
      setDetail(null);
      setSelectedIssueId("");
      setSelectedRepo("");
      return;
    }
    const selectedStillVisible = filteredRows.some((row) => row.issue_id === selectedIssueId && row.repo === selectedRepo);
    if (!selectedStillVisible) {
      setSelectedIssueId(filteredRows[0].issue_id);
      setSelectedRepo(filteredRows[0].repo);
    }
  }, [filteredRows, selectedIssueId, selectedRepo]);

  useEffect(() => {
    if (!selectedIssueId || !selectedRepo) {
      return;
    }
    let cancelled = false;

    async function loadDetail() {
      try {
        const nextDetail = await fetchJson<IssueDetailPayload>(
          `/api/issue-detail?repo=${encodeURIComponent(selectedRepo)}&issue_id=${encodeURIComponent(selectedIssueId)}`,
        );
        if (!cancelled) {
          setDetail(nextDetail);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load issue detail.");
        }
      }
    }

    void loadDetail();
    const timer = window.setInterval(() => void loadDetail(), refreshMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [refreshMs, selectedIssueId, selectedRepo]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandPaletteOpen((value) => !value);
      } else if (event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (event.key === "Escape") {
        setCommandPaletteOpen(false);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        if (!filteredRows.length) {
          return;
        }
        const index = filteredRows.findIndex((row) => row.issue_id === selectedIssueId && row.repo === selectedRepo);
        const next = filteredRows[Math.min(filteredRows.length - 1, Math.max(0, index + 1))];
        setSelectedIssueId(next.issue_id);
        setSelectedRepo(next.repo);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (!filteredRows.length) {
          return;
        }
        const index = filteredRows.findIndex((row) => row.issue_id === selectedIssueId && row.repo === selectedRepo);
        const next = filteredRows[Math.max(0, index <= 0 ? 0 : index - 1)];
        setSelectedIssueId(next.issue_id);
        setSelectedRepo(next.repo);
      } else if (event.key === "Enter" && commandPaletteOpen && filteredRows.length) {
        event.preventDefault();
        setCommandPaletteOpen(false);
        setMobileTab("detail");
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [commandPaletteOpen, filteredRows, selectedIssueId, selectedRepo]);

  const selectedIssue = asRecord(detail?.issue);
  const selectedRepoDetails = asRecord(detail?.repo);
  const repoTrust = asRecord(selectedRepoDetails.trust);
  const repoPolicy = asRecord(selectedRepoDetails.policy);
  const attempts = Array.isArray(detail?.attempts) ? detail?.attempts : [];
  const logs = overview.logs?.lines || [];
  const reliability = overview.chart_series?.reliability || [];
  const healthRows = overview.rows || [];
  const repos = Array.from(new Set(healthRows.map((row) => String(row.repo || "")).filter(Boolean)));

  async function runCommand(command: string, repo: string, dryRun = false) {
    setBusy(true);
    try {
      const body = new URLSearchParams();
      body.set("command", command);
      body.set("repo", repo);
      if (authToken) {
        body.set("auth_token", authToken);
      }
      if (dryRun) {
        body.set("dry_run", "true");
      }
      const response = await fetch("/action", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
        redirect: "follow",
      });
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const payload = (await response.json()) as { message?: string };
        setNotice(payload.message || "Request completed.");
      } else {
        const finalUrl = new URL(response.url);
        setNotice(finalUrl.searchParams.get("msg") || `${command} requested for ${repo}.`);
      }
    } catch (commandError) {
      setNotice(commandError instanceof Error ? commandError.message : "Command failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <div className="app-atmosphere" />
      <header className="topbar">
        <div>
          <p className="eyebrow">Flow Healer</p>
          <h1>Control Center</h1>
          <p className="lede">
            Linear-grade calm for queue health, attempt evidence, and live operational telemetry.
          </p>
        </div>
        <div className="topbar-actions">
          <button className="ghost-button" onClick={() => setCommandPaletteOpen(true)} type="button">
            Command Palette
          </button>
          <button className="ghost-button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} type="button">
            {theme === "dark" ? "Light" : "Dark"} Mode
          </button>
        </div>
      </header>

      <section className="metric-strip">
        <MetricCard label="Open issues" value={formatCount(queue.summary.total)} tone="idle" />
        <MetricCard label="Running" value={formatCount(queue.summary.running)} tone="running" />
        <MetricCard label="Blocked" value={formatCount(queue.summary.blocked)} tone="blocked" />
        <MetricCard label="PR open" value={formatCount(queue.summary.pr_open)} tone="success" />
        <MetricCard label="First-pass" value={formatPercent(overview.scoreboard?.first_pass_success_rate)} tone="idle" />
      </section>

      {notice ? <div className="notice-banner">{notice}</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      <nav className="mobile-tabs">
        <button className={mobileTab === "queue" ? "active" : ""} onClick={() => setMobileTab("queue")} type="button">
          Queue
        </button>
        <button className={mobileTab === "detail" ? "active" : ""} onClick={() => setMobileTab("detail")} type="button">
          Detail
        </button>
        <button className={mobileTab === "health" ? "active" : ""} onClick={() => setMobileTab("health")} type="button">
          Health
        </button>
      </nav>

      <main className="workspace-grid">
        <section className={`pane queue-pane ${mobileTab !== "queue" ? "mobile-hidden" : ""}`}>
          <div className="pane-header">
            <div>
              <p className="eyebrow">Queue</p>
              <h2>Active issues</h2>
            </div>
            <span className="meta-pill">{filteredRows.length} visible</span>
          </div>

          <div className="view-strip">
            {(queue.views || []).map((view) => (
              <button
                key={view.id}
                className={selectedView === view.id ? "active" : ""}
                onClick={() => setSelectedView(view.id)}
                type="button"
              >
                {view.label}
                <span>{view.count}</span>
              </button>
            ))}
          </div>

          <label className="search-field">
            <span>Search</span>
            <input
              ref={searchRef}
              placeholder="Slash to focus"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>

          <div className="queue-list">
            {filteredRows.map((row) => {
              const active = row.issue_id === selectedIssueId && row.repo === selectedRepo;
              return (
                <button
                  key={`${row.repo}-${row.issue_id}`}
                  className={`queue-card ${active ? "active" : ""}`}
                  onClick={() => {
                    setSelectedIssueId(row.issue_id);
                    setSelectedRepo(row.repo);
                    setMobileTab("detail");
                  }}
                  type="button"
                >
                  <div className="queue-card-header">
                    <span className={`tone tone-${stateTone(row.state)}`}>{row.state}</span>
                    <span className="mono">#{row.issue_id}</span>
                  </div>
                  <h3>{row.title}</h3>
                  <p>{row.explanation_summary || row.failure_summary || "Queued and waiting for operator attention."}</p>
                  <div className="queue-card-footer">
                    <span>{row.repo}</span>
                    {row.pr_badge ? <span>{row.pr_badge}</span> : null}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className={`pane detail-pane ${mobileTab !== "detail" ? "mobile-hidden" : ""}`}>
          <div className="pane-header">
            <div>
              <p className="eyebrow">Issue</p>
              <h2>{String(selectedIssue.title || "Select an issue")}</h2>
            </div>
            <div className="meta-row">
              <span className={`tone tone-${stateTone(String(selectedIssue.state || ""))}`}>{String(selectedIssue.state || "idle")}</span>
              {selectedIssue.issue_id ? <span className="meta-pill">#{String(selectedIssue.issue_id)}</span> : null}
            </div>
          </div>

          <div className="tab-strip">
            {DETAIL_TABS.map((tab) => (
              <button key={tab.id} className={detailTab === tab.id ? "active" : ""} onClick={() => setDetailTab(tab.id)} type="button">
                {tab.label}
              </button>
            ))}
          </div>

          {detailTab === "detail" ? (
            <div className="detail-stack">
              <article className="surface">
                <div className="surface-header">
                  <span className="eyebrow">Summary</span>
                  <span className="meta-pill">{String(selectedRepoDetails.name || selectedRepo || "No repo")}</span>
                </div>
                <p className="body-copy">
                  {String(selectedIssue.explanation_summary || selectedIssue.failure_summary || "No issue selected yet.")}
                </p>
                <div className="detail-grid">
                  <InfoBlock label="Recommended action" value={String(selectedIssue.recommended_action || "observe_issue")} />
                  <InfoBlock label="Repo trust" value={String(repoTrust.summary || "No trust summary available.")} />
                  <InfoBlock label="Policy" value={String(repoPolicy.summary || "No policy summary available.")} />
                  <InfoBlock label="Workspace" value={String(selectedIssue.workspace_path || "Not assigned")} mono />
                </div>
              </article>

              <article className="surface">
                <div className="surface-header">
                  <span className="eyebrow">Issue body</span>
                  <span className="meta-pill">Contract</span>
                </div>
                <pre className="contract-block">{String(selectedIssue.body || "Issue body will appear here.")}</pre>
              </article>

              <article className="surface">
                <div className="surface-header">
                  <span className="eyebrow">Attempts</span>
                  <span className="meta-pill">{attempts.length}</span>
                </div>
                <div className="attempt-list">
                  {attempts.length ? (
                    attempts.map((attempt) => {
                      const runtimeSummary = asRecord(attempt.runtime_summary);
                      const testSummary = asRecord(attempt.test_summary);
                      return (
                        <div className="attempt-card" key={String(attempt.attempt_id || Math.random())}>
                          <div className="queue-card-header">
                            <span className={`tone tone-${stateTone(String(attempt.state || ""))}`}>{String(attempt.state || "unknown")}</span>
                            <span className="mono">{String(attempt.attempt_id || "")}</span>
                          </div>
                          <p>{String(attempt.failure_reason || runtimeSummary.summary || "No failure summary recorded.")}</p>
                          <div className="attempt-meta">
                            <span>Tests: {formatCount(testSummary.failed_tests)}</span>
                            <span>Started: {String(attempt.started_at || "—")}</span>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <p className="empty-copy">No attempts have been recorded for this issue yet.</p>
                  )}
                </div>
              </article>
            </div>
          ) : null}

          {detailTab === "activity" ? (
            <div className="activity-list">
              {(detail?.activity || []).map((item) => (
                <article className="activity-card" key={item.id}>
                  <div className="queue-card-header">
                    <span className={`tone tone-${activityTone(item.signal)}`}>{item.signal || item.kind}</span>
                    <span className="mono">{item.timestamp || ""}</span>
                  </div>
                  <h3>{item.summary || item.message || "Activity event"}</h3>
                  <p>{item.subsystem || item.repo || "flow-healer"}</p>
                </article>
              ))}
            </div>
          ) : null}

          {detailTab === "logs" ? (
            <article className="surface">
              <div className="surface-header">
                <span className="eyebrow">Recent logs</span>
                <span className="meta-pill">{logs.length}</span>
              </div>
              <pre className="contract-block log-block">{logs.join("\n") || "No logs captured yet."}</pre>
            </article>
          ) : null}
        </section>

        <aside className={`pane health-pane ${mobileTab !== "health" ? "mobile-hidden" : ""}`}>
          <div className="pane-header">
            <div>
              <p className="eyebrow">Health</p>
              <h2>Telemetry</h2>
            </div>
            <span className="meta-pill">{healthRows.length} repos</span>
          </div>

          <div className="tab-strip compact">
            {HEALTH_TABS.map((tab) => (
              <button key={tab.id} className={healthTab === tab.id ? "active" : ""} onClick={() => setHealthTab(tab.id)} type="button">
                {tab.label}
              </button>
            ))}
          </div>

          {healthTab === "health" ? (
            <div className="detail-stack">
              <article className="surface">
                <div className="surface-header">
                  <span className="eyebrow">Reliability trend</span>
                  <span className="meta-pill">{reliability.length} samples</span>
                </div>
                <div className="trend-list">
                  {reliability.slice(-6).map((entry, index) => (
                    <div className="trend-row" key={`${entry.day || index}`}>
                      <span>{String(entry.day || `Sample ${index + 1}`)}</span>
                      <div className="trend-bar">
                        <div style={{ width: `${Math.max(6, Math.round(Number(entry.first_pass_success_rate || 0) * 100))}%` }} />
                      </div>
                      <span>{formatPercent(entry.first_pass_success_rate)}</span>
                    </div>
                  ))}
                </div>
              </article>

              <article className="surface">
                <div className="surface-header">
                  <span className="eyebrow">Repo state</span>
                  <span className="meta-pill">Live</span>
                </div>
                <div className="attempt-list">
                  {healthRows.map((row) => (
                    <div className="attempt-card" key={String(row.repo || Math.random())}>
                      <div className="queue-card-header">
                        <span className={`tone tone-${stateTone(String(row.status || row.state || ""))}`}>{String(row.status || row.state || "idle")}</span>
                        <span className="mono">{String(row.repo || "")}</span>
                      </div>
                      <p>{String(asRecord(row.trust).summary || asRecord(row.policy).summary || "No runtime summary available.")}</p>
                    </div>
                  ))}
                </div>
              </article>
            </div>
          ) : null}

          {healthTab === "actions" ? (
            <div className="detail-stack">
              <article className="surface">
                <div className="surface-header">
                  <span className="eyebrow">Operator actions</span>
                  <span className="meta-pill">Secondary</span>
                </div>
                <label className="search-field">
                  <span>{bootstrap.authMode === "token" ? `Token (${bootstrap.authTokenEnv})` : "Auth token"}</span>
                  <input
                    type="password"
                    placeholder="Optional until mutation is required"
                    value={authToken}
                    onChange={(event) => setAuthToken(event.target.value)}
                  />
                </label>
                <div className="action-grid">
                  {repos.map((repo) => (
                    <div className="action-card" key={repo}>
                      <h3>{repo}</h3>
                      <div className="action-buttons">
                        <button disabled={busy} onClick={() => void runCommand("status", repo)} type="button">Status</button>
                        <button disabled={busy} onClick={() => void runCommand("doctor", repo)} type="button">Doctor</button>
                        <button disabled={busy} onClick={() => void runCommand("once", repo)} type="button">Run once</button>
                        <button disabled={busy} onClick={() => void runCommand("scan", repo, true)} type="button">Dry scan</button>
                      </div>
                    </div>
                  ))}
                </div>
              </article>
            </div>
          ) : null}
        </aside>
      </main>

      {commandPaletteOpen ? (
        <div className="palette-backdrop" onClick={() => setCommandPaletteOpen(false)} role="presentation">
          <div className="palette" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <div className="surface-header">
              <span className="eyebrow">Command palette</span>
              <button className="ghost-button" onClick={() => setCommandPaletteOpen(false)} type="button">
                Close
              </button>
            </div>
            <div className="palette-group">
              <h3>Views</h3>
              {(queue.views || []).map((view) => (
                <button
                  key={view.id}
                  className="palette-row"
                  onClick={() => {
                    setSelectedView(view.id);
                    setCommandPaletteOpen(false);
                  }}
                  type="button"
                >
                  <span>{view.label}</span>
                  <span>{view.count}</span>
                </button>
              ))}
            </div>
            <div className="palette-group">
              <h3>Quick actions</h3>
              <button className="palette-row" onClick={() => setMobileTab("queue")} type="button">
                <span>Focus queue</span>
                <span>/</span>
              </button>
              <button className="palette-row" onClick={() => setMobileTab("health")} type="button">
                <span>Open health</span>
                <span>H</span>
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <article className="metric-card">
      <span className="eyebrow">{label}</span>
      <div className="metric-value-row">
        <strong>{value}</strong>
        <span className={`tone tone-${tone}`}>{tone}</span>
      </div>
    </article>
  );
}

function InfoBlock({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="info-block">
      <span className="eyebrow">{label}</span>
      <p className={mono ? "mono" : ""}>{value}</p>
    </div>
  );
}
