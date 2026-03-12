"use client";

import React from "react";
import { useEffect, useState } from "react";

import { AppFrame } from "@/components/dashboard/app-frame";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { getOverviewData, type DataSourceState, type OverviewPayload } from "@/lib/flow-healer";

export function TelemetryOverview() {
  const [overview, setOverview] = useState<OverviewPayload>({ rows: [], logs: { lines: [] }, activity: [] });
  const [source, setSource] = useState<DataSourceState>({ mode: "fallback" });

  useEffect(() => {
    let active = true;

    const refresh = async () => {
      const result = await getOverviewData();
      if (!active) return;
      setOverview(result.data);
      setSource(result.source);
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

  return (
    <AppFrame title="Telemetry" subtitle="Compact health, reliability, and runtime signal surfaces." source={source}>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="panel p-5">
          <p className="eyebrow">Reliability</p>
          <h2 className="text-lg font-semibold tracking-tight">Recent trend</h2>
          <div className="mt-6 space-y-3">
            {(overview.chart_series?.reliability || []).map((entry, index) => (
              <div key={String(entry.day || index)} className="flex items-center gap-4 rounded-2xl border bg-background/60 px-4 py-3">
                <span className="w-16 text-sm text-muted-foreground">{String(entry.day || "Sample")}</span>
                <div className="h-2 flex-1 rounded-full bg-secondary">
                  <div
                    className="h-2 rounded-full bg-primary"
                    style={{ width: `${Math.max(8, Math.round(Number(entry.first_pass_success_rate || 0) * 100))}%` }}
                  />
                </div>
                <span className="text-sm font-medium">{Math.round(Number(entry.first_pass_success_rate || 0) * 100)}%</span>
              </div>
            ))}
          </div>
        </section>
        <aside className="space-y-4">
          <Collapsible defaultOpen className="panel p-4">
            <CollapsibleTrigger className="w-full text-left">
              <div className="flex items-center justify-between">
                <div>
                  <p className="eyebrow">Repos</p>
                  <h3 className="font-semibold">Runtime health</h3>
                </div>
                <Badge>{overview.rows.length}</Badge>
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-4 space-y-3">
              {overview.rows.map((row, index) => (
                <div key={index} className="rounded-2xl border bg-background/60 p-4">
                  <p className="font-medium">{String(row.repo || "flow-healer")}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{String((row.trust as { summary?: string })?.summary || (row.policy as { summary?: string })?.summary || "No runtime summary.")}</p>
                </div>
              ))}
            </CollapsibleContent>
          </Collapsible>
          <Collapsible defaultOpen className="panel p-4">
            <CollapsibleTrigger className="w-full text-left">
              <div>
                <p className="eyebrow">Logs</p>
                <h3 className="font-semibold">Recent output</h3>
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-4 space-y-2">
              {(overview.logs?.lines || []).map((line, index) => (
                <pre key={index} className="overflow-auto rounded-xl border bg-background/60 p-3 text-xs text-muted-foreground">
                  {line}
                </pre>
              ))}
            </CollapsibleContent>
          </Collapsible>
        </aside>
      </div>
    </AppFrame>
  );
}
