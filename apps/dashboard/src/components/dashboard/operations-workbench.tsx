"use client";

import React from "react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Command, FileWarning, LayoutGrid, List, Search, SlidersHorizontal } from "lucide-react";

import { AppFrame } from "@/components/dashboard/app-frame";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
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

const SECTION_LABELS = ["Summary", "Attempts", "Validation", "Artifacts", "Activity"] as const;

function toneForState(state: string) {
  if (["running", "claimed", "verify_pending"].includes(state)) return "info";
  if (["blocked", "failed"].includes(state)) return "danger";
  if (["pr_open", "pr_pending_approval"].includes(state)) return "success";
  return "default";
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
  const [commandOpen, setCommandOpen] = useState(false);
  const [queueSource, setQueueSource] = useState<DataSourceState>({ mode: initialQueue ? "live" : "fallback" });
  const [overviewSource, setOverviewSource] = useState<DataSourceState>({ mode: initialOverview ? "live" : "fallback" });
  const [detailSource, setDetailSource] = useState<DataSourceState>({ mode: initialIssueId ? "live" : "fallback" });
  const [sections, setSections] = useState<Record<string, boolean>>({
    Summary: true,
    Attempts: true,
    Validation: true,
    Artifacts: true,
    Activity: true,
  });

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

  const rows = useMemo(() => {
    const text = query.trim().toLowerCase();
    return queue.rows.filter((row) => {
      if (!text) return true;
      return [row.title, row.repo, row.issue_id, row.explanation_summary].join(" ").toLowerCase().includes(text);
    });
  }, [queue.rows, query]);

  const selectedRow = rows.find((row) => row.issue_id === issueId) || queue.rows.find((row) => row.issue_id === issueId) || rows[0];

  return (
    <AppFrame
      title="Operations"
      subtitle="A Linear-style workbench for queue health, telemetry, and issue detail."
      source={source}
      actions={
        <>
          <Button variant="outline" onClick={() => setCommandOpen(true)}>
            <Command className="h-4 w-4" />
            Search
          </Button>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline">
                <SlidersHorizontal className="h-4 w-4" />
                Display
              </Button>
            </PopoverTrigger>
            <PopoverContent className="space-y-4">
              <div>
                <p className="eyebrow mb-2">View mode</p>
                <div className="grid grid-cols-2 gap-2">
                  <Button variant={displayMode === "list" ? "default" : "outline"} onClick={() => setDisplayMode("list")}>
                    <List className="h-4 w-4" />
                    List
                  </Button>
                  <Button variant={displayMode === "board" ? "default" : "outline"} onClick={() => setDisplayMode("board")}>
                    <LayoutGrid className="h-4 w-4" />
                    Board
                  </Button>
                </div>
              </div>
              <Separator className="h-px w-full" />
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>Dense rows are the default. Use board view for state grouping and quick status scans.</p>
              </div>
            </PopoverContent>
          </Popover>
        </>
      }
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="panel overflow-hidden p-0">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <p className="eyebrow">Queue</p>
              <h2 className="text-lg font-semibold tracking-tight">Live issues</h2>
            </div>
            <div className="flex items-center gap-2">
              <Badge>{queue.summary.total || rows.length} total</Badge>
              <Badge variant="danger">{queue.summary.blocked || 0} blocked</Badge>
            </div>
          </div>
          <div className="border-b px-5 py-3">
            <div className="flex flex-wrap gap-2">
              {queue.views.map((view) => (
                <Badge key={view.id}>{view.label} {view.count}</Badge>
              ))}
            </div>
            <div className="mt-3">
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter queue" />
            </div>
          </div>
          <ScrollArea className="h-[680px]">
            {displayMode === "list" ? (
              <div className="divide-y">
                {rows.map((row) => (
                  <button
                    key={row.issue_id}
                    onClick={() => setIssueId(row.issue_id)}
                    className={cn(
                      "flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-secondary/60",
                      selectedRow?.issue_id === row.issue_id && "bg-secondary/80",
                    )}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant={toneForState(row.state) as never}>{row.state}</Badge>
                        <span className="font-mono text-xs text-muted-foreground">#{row.issue_id}</span>
                        <span className="text-xs text-muted-foreground">{row.repo}</span>
                      </div>
                      <p className="mt-2 truncate font-medium tracking-tight">{row.title}</p>
                      <p className="mt-1 truncate text-sm text-muted-foreground">
                        {row.explanation_summary || row.failure_summary || "No summary available."}
                      </p>
                    </div>
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </button>
                ))}
              </div>
            ) : (
              <div className="grid gap-4 p-5 md:grid-cols-3">
                {["running", "blocked", "pr_open"].map((state) => (
                  <div key={state} className="panel-soft p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="font-medium capitalize">{state.replace("_", " ")}</h3>
                      <Badge variant={toneForState(state) as never}>{rows.filter((row) => row.state === state).length}</Badge>
                    </div>
                    <div className="space-y-3">
                      {rows.filter((row) => row.state === state).map((row) => (
                        <button
                          key={row.issue_id}
                          onClick={() => setIssueId(row.issue_id)}
                          className="w-full rounded-xl border bg-background/60 p-3 text-left transition hover:bg-background"
                        >
                          <p className="font-medium">{row.title}</p>
                          <p className="mt-1 text-sm text-muted-foreground">#{row.issue_id}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </section>

        <aside className="panel flex min-h-[680px] flex-col p-4">
          <div className="mb-4">
            <p className="eyebrow">Inspector</p>
            <h2 className="text-lg font-semibold tracking-tight">{selectedRow?.title || "Issue detail"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {selectedRow?.explanation_summary || selectedRow?.failure_summary || "Select an issue to inspect attempts and artifacts."}
            </p>
          </div>
          <Tabs defaultValue="detail" className="flex-1">
            <TabsList className="mb-4 grid w-full grid-cols-2">
              <TabsTrigger value="detail">Detail</TabsTrigger>
              <TabsTrigger value="activity">Activity</TabsTrigger>
            </TabsList>
            <TabsContent value="detail" className="space-y-3">
              {SECTION_LABELS.map((label) => (
                <Collapsible
                  key={label}
                  open={sections[label]}
                  onOpenChange={(open) => setSections((current) => ({ ...current, [label]: open }))}
                  className="panel-soft overflow-hidden"
                >
                  <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left">
                    <span className="font-medium">{label}</span>
                    <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition", sections[label] && "rotate-180")} />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="border-t px-4 py-3 text-sm text-muted-foreground">
                    {label === "Summary" && (
                      <div className="space-y-2">
                        <p>{String(detail?.repo?.policy ? "Policy context is available for this issue." : "Issue summary is ready for review.")}</p>
                        <p className="font-mono text-xs text-muted-foreground">{String(detail?.issue?.issue_id || selectedRow?.issue_id || "")}</p>
                      </div>
                    )}
                    {label === "Attempts" && (
                      <div className="space-y-2">
                        {(detail?.attempts || []).map((attempt) => (
                          <div key={String(attempt.attempt_id)} className="rounded-xl border bg-background/60 p-3">
                            <p className="font-mono text-xs text-muted-foreground">{String(attempt.attempt_id)}</p>
                            <p className="mt-2 text-foreground">{String(attempt.failure_reason || attempt.state || "No attempt summary.")}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    {label === "Validation" && <p>Targeted validation summaries and verifier output live here.</p>}
                    {label === "Artifacts" && (
                      <div className="space-y-2">
                        <Link href="/artifacts" className="text-primary hover:underline">
                          Open the artifact browser
                        </Link>
                      </div>
                    )}
                    {label === "Activity" && <p>Recent issue activity stays collapsible so the inspector remains sleek by default.</p>}
                  </CollapsibleContent>
                </Collapsible>
              ))}
            </TabsContent>
            <TabsContent value="activity" className="space-y-3">
              {(overview.activity || []).map((item, index) => (
                <div key={String(item.id || index)} className="panel-soft p-4">
                  <div className="flex items-center gap-2">
                    <Badge variant={toneForState(String(item.signal || "default")) as never}>{String(item.signal || "event")}</Badge>
                    <span className="text-xs text-muted-foreground">{String(item.repo || "flow-healer")}</span>
                  </div>
                  <p className="mt-3 text-sm text-foreground">{String(item.summary || item.message || "Runtime activity event")}</p>
                </div>
              ))}
            </TabsContent>
          </Tabs>
        </aside>
      </div>

      <Dialog open={commandOpen} onOpenChange={setCommandOpen}>
        <DialogContent>
          <div className="space-y-4">
            <div>
              <p className="eyebrow">Command menu</p>
              <h2 className="mt-1 text-lg font-semibold tracking-tight">Jump faster</h2>
            </div>
            <div className="flex items-center gap-2 rounded-xl border px-3 py-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Input className="border-0 bg-transparent p-0 focus-visible:ring-0" placeholder="Search issues, routes, or views" />
            </div>
            <div className="space-y-2">
              <Button variant="ghost" className="w-full justify-start" onClick={() => setDisplayMode("list")}>
                <List className="h-4 w-4" />
                Switch to list view
              </Button>
              <Button variant="ghost" className="w-full justify-start" onClick={() => setDisplayMode("board")}>
                <LayoutGrid className="h-4 w-4" />
                Switch to board view
              </Button>
              <Button variant="ghost" className="w-full justify-start" asChild>
                <Link href="/telemetry">
                  <FileWarning className="h-4 w-4" />
                  Open telemetry
                </Link>
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </AppFrame>
  );
}
