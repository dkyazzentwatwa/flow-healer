export type QueueRow = {
  issue_id: string;
  repo: string;
  title: string;
  state: string;
  explanation_summary?: string;
  failure_summary?: string;
  recommended_action?: string;
  pr_badge?: string;
  view_memberships?: string[];
};

export type QueuePayload = {
  rows: QueueRow[];
  views: Array<{ id: string; label: string; count: number }>;
  summary: Record<string, number>;
};

export type OverviewPayload = {
  rows: Array<Record<string, unknown>>;
  activity?: Array<Record<string, unknown>>;
  logs?: { lines?: string[]; files?: string[] };
  scoreboard?: Record<string, number>;
  chart_series?: {
    reliability?: Array<Record<string, unknown>>;
  };
};

export type IssueDetailPayload = {
  found?: boolean;
  issue?: Record<string, unknown>;
  repo?: Record<string, unknown>;
  attempts?: Array<Record<string, unknown>>;
  activity?: Array<Record<string, unknown>>;
};

export type ArtifactEntry = {
  id: string;
  label: string;
  kind: string;
  repo: string;
  issue: string;
  href: string;
};

export type DataSourceState = {
  mode: "live" | "fallback";
  error?: string;
};

export type DataResult<T> = {
  data: T;
  source: DataSourceState;
};

const demoQueue: QueuePayload = {
  rows: [
    {
      issue_id: "676",
      repo: "flow-healer",
      title: "Risk guardrail edge cases",
      state: "blocked",
      explanation_summary: "Validation passed but verifier still rejected boolean numeric inputs.",
      view_memberships: ["all", "blocked", "needs_review"],
    },
    {
      issue_id: "670",
      repo: "flow-healer",
      title: "Dashboard reset planning",
      state: "pr_open",
      explanation_summary: "Next app shell is being split from the Python runtime.",
      pr_badge: "#670",
      view_memberships: ["all", "pr_open"],
    },
    {
      issue_id: "663",
      repo: "flow-healer",
      title: "Telemetry view density tuning",
      state: "running",
      explanation_summary: "Live activity stream is polling and new evidence is landing.",
      view_memberships: ["all", "running"],
    },
  ],
  views: [
    { id: "all", label: "All issues", count: 3 },
    { id: "running", label: "Running", count: 1 },
    { id: "blocked", label: "Blocked", count: 1 },
    { id: "pr_open", label: "PR Open", count: 1 },
    { id: "needs_review", label: "Needs review", count: 1 },
  ],
  summary: {
    total: 3,
    running: 1,
    blocked: 1,
    pr_open: 1,
    needs_review: 1,
  },
};

const demoOverview: OverviewPayload = {
  rows: [
    {
      repo: "flow-healer",
      status: "blocked",
      trust: { summary: "One blocked issue needs operator review." },
      policy: { summary: "Autonomous healing can continue after that review." },
    },
  ],
  logs: {
    lines: [
      "[flow-healer.log] 2026-03-12 00:31:04 INFO queue refreshed",
      "[flow-healer.log] 2026-03-12 00:31:07 WARN verifier soft-failed on issue #676",
    ],
  },
  activity: [
    { id: "act-1", signal: "running", summary: "Issue #663 is still running", repo: "flow-healer" },
    { id: "act-2", signal: "failure", summary: "Issue #676 needs review", repo: "flow-healer" },
  ],
  scoreboard: {
    first_pass_success_rate: 0.67,
    issue_successes: 12,
    issue_failures: 4,
  },
  chart_series: {
    reliability: [
      { day: "Mon", first_pass_success_rate: 0.5 },
      { day: "Tue", first_pass_success_rate: 0.6 },
      { day: "Wed", first_pass_success_rate: 0.75 },
      { day: "Thu", first_pass_success_rate: 0.67 },
    ],
  },
};

const demoDetails: Record<string, IssueDetailPayload> = {
  "676": {
    found: true,
    issue: {
      issue_id: "676",
      title: "Risk guardrail edge cases",
      state: "blocked",
      body: "Required code outputs:\n- e2e-apps/nobi-owl-trader/api/risk.py\n- e2e-apps/nobi-owl-trader/tests/test_risk.py",
      failure_summary: "Verifier still rejects bool as finite numeric input.",
      recommended_action: "inspect_verifier_feedback",
    },
    repo: {
      name: "flow-healer",
      trust: { summary: "Verifier is soft-failing after otherwise healthy validation." },
      policy: { summary: "Scope is safe; a narrow retry is still reasonable." },
    },
    attempts: [
      {
        attempt_id: "ha_676_2",
        state: "failed",
        failure_reason: "Bool still treated as int inside finite number guard.",
        artifact_links: [
          {
            label: "failure_screenshot",
            target: "/tmp/flow-healer-browser/issue-676.png",
            web_href: "/artifact?path=%2Ftmp%2Fflow-healer-browser%2Fissue-676.png",
          },
          {
            label: "verifier_transcript",
            target: "/tmp/flow-healer-browser/issue-676.txt",
            web_href: "/artifact?path=%2Ftmp%2Fflow-healer-browser%2Fissue-676.txt",
          },
        ],
      },
    ],
    activity: [
      { id: "detail-1", signal: "failure", summary: "Verifier soft-failed after passing tests." },
    ],
  },
};

const demoArtifacts: ArtifactEntry[] = [
  {
    id: "artifact-1",
    label: "Failure screenshot",
    kind: "image",
    repo: "flow-healer",
    issue: "676",
    href: "/api/flow-healer/artifact?path=%2Ftmp%2Fflow-healer-browser%2Fissue-676.png",
  },
  {
    id: "artifact-2",
    label: "Verifier transcript",
    kind: "text",
    repo: "flow-healer",
    issue: "676",
    href: "/api/flow-healer/artifact?path=%2Ftmp%2Fflow-healer-browser%2Fissue-676.txt",
  },
];

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unable to reach Flow Healer.";
}

async function fetchWithFallback<T>(path: string, fallback: T): Promise<DataResult<T>> {
  try {
    const data = await fetchJson<T>(path);
    return { data, source: { mode: "live" } };
  } catch (error) {
    return { data: fallback, source: { mode: "fallback", error: errorMessage(error) } };
  }
}

function mergeSources(...sources: DataSourceState[]): DataSourceState {
  const fallback = sources.find((source) => source.mode === "fallback");
  return fallback ? fallback : { mode: "live" };
}

function artifactKindFromLink(link: Record<string, unknown>) {
  const text = `${String(link.label || "")} ${String(link.target || "")} ${String(link.web_href || "")}`.toLowerCase();
  if (/\.(png|jpe?g|gif|webp|svg)\b/.test(text) || text.includes("screenshot") || text.includes("image")) {
    return "image";
  }
  return "text";
}

function titleizeArtifactLabel(label: string) {
  return label
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function normalizeArtifactHref(href: string) {
  if (!href) return href;
  if (href.startsWith("/api/flow-healer/")) return href;
  if (href.startsWith("/artifact")) return `/api/flow-healer${href}`;
  return href;
}

export function extractArtifactsFromIssueDetail(
  detail: IssueDetailPayload,
  context: { repo: string; issueId: string },
): ArtifactEntry[] {
  const attempts = Array.isArray(detail.attempts) ? detail.attempts : [];

  return attempts.flatMap((attempt, attemptIndex) => {
    const artifactLinks = Array.isArray(attempt.artifact_links) ? attempt.artifact_links : [];
    const attemptId = String(attempt.attempt_id || `attempt-${attemptIndex + 1}`);

    return artifactLinks
      .filter((link): link is Record<string, unknown> => Boolean(link) && typeof link === "object")
      .map((link, linkIndex) => {
        const label = String(link.label || `artifact_${linkIndex + 1}`);
        return {
          id: `${context.issueId}-${attemptId}-${label}-${linkIndex}`,
          label: titleizeArtifactLabel(label),
          kind: artifactKindFromLink(link),
          repo: context.repo,
          issue: context.issueId,
          href: normalizeArtifactHref(String(link.web_href || link.target || "")),
        };
      })
      .filter((artifact) => artifact.href);
  });
}

export async function getQueueData(): Promise<DataResult<QueuePayload>> {
  return fetchWithFallback<QueuePayload>("/api/flow-healer/api/queue", demoQueue);
}

export async function getOverviewData(): Promise<DataResult<OverviewPayload>> {
  return fetchWithFallback<OverviewPayload>("/api/flow-healer/api/overview", demoOverview);
}

export async function getIssueDetailData(issueId: string, repo = "flow-healer"): Promise<DataResult<IssueDetailPayload>> {
  return fetchWithFallback<IssueDetailPayload>(
    `/api/flow-healer/api/issue-detail?repo=${encodeURIComponent(repo)}&issue_id=${encodeURIComponent(issueId)}`,
    demoDetails[issueId] || { found: false, issue: {}, repo: {}, attempts: [], activity: [] },
  );
}

export async function getArtifactsData(): Promise<DataResult<ArtifactEntry[]>> {
  const queueResult = await getQueueData();
  const rows = queueResult.data.rows.slice(0, 24);

  if (!rows.length) {
    return {
      data: demoArtifacts,
      source: queueResult.source.mode === "live" ? { mode: "fallback", error: "No issue rows returned for artifact discovery." } : queueResult.source,
    };
  }

  const detailResults = await Promise.all(
    rows.map(async (row) => ({
      row,
      result: await getIssueDetailData(row.issue_id, row.repo),
    })),
  );

  const artifacts = detailResults.flatMap(({ row, result }) =>
    extractArtifactsFromIssueDetail(result.data, { repo: row.repo, issueId: row.issue_id }),
  );

  if (!artifacts.length) {
    const source = mergeSources(queueResult.source, ...detailResults.map(({ result }) => result.source));
    return {
      data: source.mode === "live" ? [] : demoArtifacts,
      source:
        source.mode === "live"
          ? { mode: "live" }
          : { mode: "fallback", error: source.error || "No artifact evidence was available from the backend." },
    };
  }

  return {
    data: artifacts,
    source: mergeSources(queueResult.source, ...detailResults.map(({ result }) => result.source)),
  };
}

export async function getQueue(): Promise<QueuePayload> {
  return (await getQueueData()).data;
}

export async function getOverview(): Promise<OverviewPayload> {
  return (await getOverviewData()).data;
}

export async function getIssueDetail(issueId: string, repo = "flow-healer"): Promise<IssueDetailPayload> {
  return (await getIssueDetailData(issueId, repo)).data;
}

export async function getArtifacts(): Promise<ArtifactEntry[]> {
  return (await getArtifactsData()).data;
}

export { demoOverview, demoQueue };
