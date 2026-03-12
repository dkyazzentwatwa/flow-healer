"use client";

import React from "react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis } from "recharts";
import { LayoutGrid, List, Search } from "lucide-react";

import { AppFrame } from "@/components/dashboard/app-frame";
import { CollapsibleCard } from "@/components/dashboard/collapsible-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, type ChartConfig, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getIssueDetailData,
  getOverviewData,
  getQueueData,
  type DataSourceState,
  type IssueDetailPayload,
  type OverviewPayload,
  type QueuePayload,
} from "@/lib/flow-healer";
import { cn } from "@/lib/utils";

const stateChartConfig = {
  value: { label: "Issues", color: "hsl(0 0% 98%)" },
} satisfies ChartConfig;

const queueViewsChartConfig = {
  count: { label: "Issues", color: "hsl(0 0% 82%)" },
} satisfies ChartConfig;

const reliabilityChartConfig = {
  value: { label: "Reliability", color: "hsl(0 0% 92%)" },
} satisfies ChartConfig;

const pieColors = ["hsl(0 0% 96%)", "hsl(0 0% 78%)", "hsl(0 0% 62%)", "hsl(0 0% 45%)", "hsl(0 0% 32%)"];

function toneForState(state: string) {
  if (["running", "claimed", "verify_pending"].includes(state)) return "info";
  if (["blocked", "failed"].includes(state)) return "danger";
  if (["pr_open", "pr_pending_approval"].includes(state)) return "success";
  return "default";
}

function LiveDataUnavailable() {
  return (
    <div className="flex min-h-[220px] items-center justify-center rounded-md border border-dashed border-border/70 bg-background/40 p-4 text-center text-sm text-muted-foreground">
      Live data unavailable
    </div>
  );
}

function NoLiveDatapoints({ message = "No live data points available yet." }: { message?: string }) {
  return (
    <div className="flex min-h-[220px] items-center justify-center rounded-md border border-dashed border-border/70 bg-background/40 p-4 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

export function OperationsWorkbench({
  initialQueue,
  initialOverview,
  initialIssueId,
}: {
  initialQueue?: QueuePayload;
  initialOverview?: OverviewPayload;
  initialIssueId?: string;
}) {
  const [queue, setQueue] = useState<QueuePayload>(initialQueue ?? { rows: [], views: [], summary: {} });
  const [overview, setOverview] = useState<OverviewPayload>(initialOverview ?? { rows: [], logs: { lines: [] }, activity: [] });
  const [issueId, setIssueId] = useState(initialIssueId || initialQueue?.rows[0]?.issue_id || "");
  const [detail, setDetail] = useState<IssueDetailPayload | null>(null);
  const [query, setQuery] = useState("");
  const [displayMode, setDisplayMode] = useState<"list" | "board">("list");
  const [queueSource, setQueueSource] = useState<DataSourceState>({ mode: initialQueue ? "live" : "fallback" });
  const [overviewSource, setOverviewSource] = useState<DataSourceState>({ mode: initialOverview ? "live" : "fallback" });
  const [detailSource, setDetailSource] = useState<DataSourceState>({ mode: initialIssueId ? "live" : "fallback" });
  const [issueModalOpen, setIssueModalOpen] = useState(false);

  useEffect(() => {
    let active = true;

    const refresh = async () => {
      const [queueResult, overviewResult] = await Promise.all([getQueueData(), getOverviewData()]);
      if (!active) return;
      setQueue(queueResult.data);
      setOverview(overviewResult.data);
      setQueueSource(queueResult.source);
      setOverviewSource(overviewResult.source);
    };

    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, 8000);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let active = true;
    const selected = issueId || queue.rows[0]?.issue_id;
    if (!selected) return;
    setIssueId(selected);
    const repo = queue.rows.find((row) => row.issue_id === selected)?.repo || "flow-healer";
    const refresh = async () => {
      const result = await getIssueDetailData(selected, repo);
      if (!active) return;
      setDetail(result.data);
      setDetailSource(result.source);
    };

    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, 10000);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [issueId, queue.rows]);

  const source =
    queueSource.mode === "fallback" || overviewSource.mode === "fallback" || detailSource.mode === "fallback"
      ? { mode: "fallback" as const, error: queueSource.error || overviewSource.error || detailSource.error }
      : { mode: "live" as const };

  const isLive = source.mode === "live";

  const rows = useMemo(() => {
    const text = query.trim().toLowerCase();
    return queue.rows.filter((row) => {
      if (!text) return true;
      return [row.title, row.repo, row.issue_id, row.explanation_summary].join(" ").toLowerCase().includes(text);
    });
  }, [queue.rows, query]);

  const selectedRow = rows.find((row) => row.issue_id === issueId) || queue.rows.find((row) => row.issue_id === issueId) || rows[0];

  const stateDistribution = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((row) => counts.set(row.state, (counts.get(row.state) || 0) + 1));
    return [...counts.entries()].map(([state, value]) => ({ state, value }));
  }, [rows]);

  const queueViewCounts = useMemo(
    () => queue.views.map((view) => ({ label: view.label.replace(/\s+/g, " "), count: Number(view.count || 0) })),
    [queue.views],
  );

  const reliabilitySeries = useMemo(
    () =>
      (overview.chart_series?.reliability || []).map((entry, index) => ({
        day: String(entry.day || `S${index + 1}`),
        value: Math.round(Number(entry.first_pass_success_rate || 0) * 100),
      })),
    [overview.chart_series?.reliability],
  );

  const attemptsByState = useMemo(() => {
    const attempts = Array.isArray(detail?.attempts) ? detail?.attempts : [];
    const counts = new Map<string, number>();
    attempts.forEach((attempt) => {
      const key = String(attempt.state || "unknown");
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    return [...counts.entries()].map(([name, value]) => ({ name, value }));
  }, [detail?.attempts]);

  const issueActivity = Array.isArray(detail?.activity) && detail?.activity.length ? detail.activity : overview.activity || [];
  const hasReliabilitySeries = reliabilitySeries.length > 0;
  const hasAttemptsByState = attemptsByState.length > 0;

  const metricCards = [
    { label: "Total issues", value: queue.summary.total || rows.length },
    { label: "Running", value: queue.summary.running || rows.filter((row) => row.state === "running").length },
    { label: "Blocked", value: queue.summary.blocked || rows.filter((row) => row.state === "blocked").length },
    { label: "PR open", value: queue.summary.pr_open || rows.filter((row) => row.state === "pr_open").length },
  ];

  const openIssueModal = (nextIssueId: string) => {
    setIssueId(nextIssueId);
    // Defer open to avoid Radix outside-click close race from the same pointer event.
    queueMicrotask(() => setIssueModalOpen(true));
  };

  return (
    <AppFrame
      title="Operations"
      subtitle="Mobile-first command center for queue health, issue routing, and execution analytics."
      source={source}
      actions={
        <Button variant="outline" size="sm">
          <Search className="h-4 w-4" />
          Search
        </Button>
      }
    >
      <CollapsibleCard title="Live metrics" description="Real-time queue totals" defaultOpen>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {metricCards.map((metric) => (
            <Card key={metric.label} className="bg-card/85 p-4">
              <p className="text-xs text-muted-foreground">{metric.label}</p>
              <p className="metric-value mt-1">{isLive ? metric.value : "—"}</p>
            </Card>
          ))}
        </div>
      </CollapsibleCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <CollapsibleCard title="Queue analytics" description="State distribution" defaultOpen>
          {isLive ? (
            <ChartContainer config={stateChartConfig} className="min-h-[240px] w-full">
              <BarChart accessibilityLayer data={stateDistribution}>
                <CartesianGrid vertical={false} strokeDasharray="2 4" />
                <XAxis dataKey="state" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="value" fill="var(--color-value)" radius={6} />
              </BarChart>
            </ChartContainer>
          ) : (
            <LiveDataUnavailable />
          )}
        </CollapsibleCard>

        <CollapsibleCard title="Queue view counts" description="Issue counts by backend queue views" defaultOpen>
          {isLive ? (
            <ChartContainer config={queueViewsChartConfig} className="min-h-[240px] w-full">
              <BarChart accessibilityLayer data={queueViewCounts}>
                <CartesianGrid vertical={false} strokeDasharray="2 4" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="count" fill="var(--color-count)" radius={6} />
              </BarChart>
            </ChartContainer>
          ) : (
            <LiveDataUnavailable />
          )}
        </CollapsibleCard>
      </div>

      <CollapsibleCard
        title="Live queue"
        description="Search, triage, and open issue details in modal view."
        defaultOpen
        headerRight={
          <div className="flex items-center gap-2">
            <Button variant={displayMode === "list" ? "default" : "outline"} size="sm" onClick={() => setDisplayMode("list")}>
              <List className="h-4 w-4" />
              List
            </Button>
            <Button variant={displayMode === "board" ? "default" : "outline"} size="sm" onClick={() => setDisplayMode("board")}>
              <LayoutGrid className="h-4 w-4" />
              Board
            </Button>
          </div>
        }
        contentClassName="space-y-3"
      >
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by issue, repo, or summary" />

        <ScrollArea className="h-[430px] pr-3">
          {displayMode === "list" ? (
            <div className="space-y-2">
              {rows.map((row) => (
                <button
                  key={row.issue_id}
                  onClick={() => openIssueModal(row.issue_id)}
                  className={cn(
                    "w-full rounded-lg border border-border/70 bg-background/50 p-3 text-left transition hover:bg-secondary/60",
                    selectedRow?.issue_id === row.issue_id && "border-foreground/20 bg-secondary/80",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <Badge variant={toneForState(row.state) as never}>{row.state}</Badge>
                    <span className="font-mono text-[11px] text-muted-foreground">#{row.issue_id}</span>
                    <span className="text-[11px] text-muted-foreground">{row.repo}</span>
                  </div>
                  <p className="mt-2 text-sm font-semibold tracking-tight">{row.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                    {row.explanation_summary || row.failure_summary || "No summary available."}
                  </p>
                </button>
              ))}
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-3">
              {["running", "blocked", "pr_open"].map((state) => (
                <div key={state} className="rounded-lg border border-border/70 bg-background/40 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">{state.replace("_", " ")}</p>
                    <Badge variant={toneForState(state) as never}>{rows.filter((row) => row.state === state).length}</Badge>
                  </div>
                  <div className="space-y-2">
                    {rows
                      .filter((row) => row.state === state)
                      .map((row) => (
                        <button
                          key={row.issue_id}
                          onClick={() => openIssueModal(row.issue_id)}
                          className="w-full rounded-md border border-border/70 bg-card/60 px-2 py-2 text-left text-xs hover:bg-card"
                        >
                          {row.title}
                        </button>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CollapsibleCard>

      <Dialog open={issueModalOpen} onOpenChange={setIssueModalOpen}>
        <DialogContent className="left-0 top-0 h-dvh w-full -translate-x-0 -translate-y-0 rounded-none p-4 sm:left-1/2 sm:top-1/2 sm:h-[min(90vh,780px)] sm:w-[min(94vw,980px)] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:p-6">
          <div className="h-full overflow-y-auto pr-1">
            <DialogTitle className="text-xl font-semibold tracking-tight">Selected issue detail</DialogTitle>
            <DialogDescription className="mt-1 text-sm text-muted-foreground">
              {selectedRow?.title || "Select an issue to inspect execution context."}
            </DialogDescription>

            <Tabs defaultValue="detail" className="mt-4">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="detail">Detail</TabsTrigger>
                <TabsTrigger value="activity">Issue activity</TabsTrigger>
              </TabsList>

              <TabsContent value="detail" className="space-y-4 pt-4">
                <CollapsibleCard title="Summary" description="Issue context and linked evidence" defaultOpen={false}>
                  <div className="space-y-2 rounded-lg border border-border/70 bg-background/40 p-3 text-xs text-muted-foreground">
                    <p className="font-mono">#{String(selectedRow?.issue_id || detail?.issue?.issue_id || "N/A")}</p>
                    <p>{String(selectedRow?.explanation_summary || selectedRow?.failure_summary || "No summary available yet.")}</p>
                    <Link href="/artifacts" className="inline-flex text-foreground underline-offset-4 hover:underline">
                      Open artifacts browser
                    </Link>
                  </div>
                </CollapsibleCard>

                <CollapsibleCard title="Reliability" description="Issue-level reliability trend" defaultOpen={false}>
                  {isLive && hasReliabilitySeries ? (
                    <ChartContainer config={reliabilityChartConfig} className="min-h-[190px] w-full">
                      <AreaChart accessibilityLayer data={reliabilitySeries}>
                        <CartesianGrid vertical={false} strokeDasharray="2 4" />
                        <XAxis dataKey="day" tickLine={false} axisLine={false} />
                        <YAxis tickLine={false} axisLine={false} allowDecimals={false} domain={[0, 100]} />
                        <ChartTooltip content={<ChartTooltipContent />} />
                        <Area type="monotone" dataKey="value" stroke="var(--color-value)" fill="var(--color-value)" fillOpacity={0.2} />
                      </AreaChart>
                    </ChartContainer>
                  ) : isLive ? (
                    <NoLiveDatapoints message="No issue-level reliability points yet." />
                  ) : (
                    <LiveDataUnavailable />
                  )}
                </CollapsibleCard>

                <CollapsibleCard title="Attempts by state" description="Attempt outcome counts" defaultOpen={false}>
                  <div className="flex flex-wrap gap-2">
                    {attemptsByState.map((entry) => (
                      <Badge key={entry.name} variant="default">
                        {entry.name}: {entry.value}
                      </Badge>
                    ))}
                    {!hasAttemptsByState && <p className="text-xs text-muted-foreground">No attempts recorded for this issue yet.</p>}
                  </div>
                </CollapsibleCard>
              </TabsContent>

              <TabsContent value="activity" className="space-y-4 pt-4">
                <CollapsibleCard title="Issue activity" description="Recent event stream" defaultOpen={false}>
                  <div className="grid grid-cols-1 gap-3">
                    {(issueActivity.length ? issueActivity : [{ summary: "No issue activity yet.", signal: "idle" }]).map((item, index) => (
                      <div key={String(item.id || index)} className="rounded-lg border border-border/70 bg-background/40 p-3">
                        <div className="flex items-center gap-2">
                          <Badge variant={toneForState(String(item.signal || "default")) as never}>{String(item.signal || "event")}</Badge>
                          <span className="text-xs text-muted-foreground">{String(item.repo || selectedRow?.repo || "flow-healer")}</span>
                        </div>
                        <p className="mt-2 text-sm text-foreground">{String(item.summary || item.message || "Runtime activity event")}</p>
                      </div>
                    ))}
                  </div>
                </CollapsibleCard>

                <CollapsibleCard title="Attempts chart" description="Hover-smooth composition" defaultOpen={false}>
                  {isLive && hasAttemptsByState ? (
                    <ChartContainer config={{ value: { label: "Attempts", color: "hsl(0 0% 92%)" } }} className="min-h-[220px] w-full">
                      <PieChart>
                        <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                        <Pie
                          dataKey="value"
                          nameKey="name"
                          data={attemptsByState}
                          innerRadius={42}
                          outerRadius={74}
                          stroke="none"
                        >
                          {attemptsByState.map((entry, index) => (
                            <Cell key={entry.name} fill={pieColors[index % pieColors.length]} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ChartContainer>
                  ) : isLive ? (
                    <NoLiveDatapoints message="No attempt-state chart points yet." />
                  ) : (
                    <LiveDataUnavailable />
                  )}
                </CollapsibleCard>
              </TabsContent>
            </Tabs>
          </div>
        </DialogContent>
      </Dialog>
    </AppFrame>
  );
}
