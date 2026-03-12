"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { AppFrame } from "@/components/dashboard/app-frame";
import { CollapsibleCard } from "@/components/dashboard/collapsible-card";
import { Badge } from "@/components/ui/badge";
import { ChartContainer, type ChartConfig, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Input } from "@/components/ui/input";
import { getQueueData, type DataSourceState } from "@/lib/flow-healer";

const settingsChartConfig = {
  count: { label: "Count", color: "hsl(0 0% 92%)" },
} satisfies ChartConfig;

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

export function SettingsPanel() {
  const [apiBaseUrl, setApiBaseUrl] = useState(process.env.NEXT_PUBLIC_FLOW_HEALER_API_BASE_URL || "http://127.0.0.1:8788");
  const [source, setSource] = useState<DataSourceState>({ mode: "fallback" });
  const [summary, setSummary] = useState<Record<string, number>>({});

  useEffect(() => {
    let active = true;
    void getQueueData().then((result) => {
      if (!active) return;
      setSource(result.source);
      setSummary(result.data.summary || {});
    });
    return () => {
      active = false;
    };
  }, []);

  const isLive = source.mode === "live";

  const summaryChart = useMemo(
    () =>
      Object.entries(summary).map(([key, value]) => ({
        label: key.replace("_", " "),
        count: Number(value || 0),
      })),
    [summary],
  );
  const hasSummaryData = summaryChart.length > 0;

  return (
    <AppFrame title="Settings" subtitle="Configuration with collapsible controls and live-only chart rendering." source={source}>
      <div className="grid gap-4 xl:grid-cols-2">
        <CollapsibleCard title="Backend target" description="Dashboard API gateway for Flow Healer runtime services." defaultOpen>
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge>{source.mode === "live" ? "Live" : "Fallback"}</Badge>
              <Badge variant="default">Local</Badge>
            </div>
            <Input value={apiBaseUrl} onChange={(event) => setApiBaseUrl(event.target.value)} />
            <p className="text-xs text-muted-foreground">
              Set <code>FLOW_HEALER_API_BASE_URL</code> before <code>npm run dev</code> if your backend is not on port 8788.
            </p>
          </div>
        </CollapsibleCard>

        <CollapsibleCard title="Queue snapshot" description="Current queue summary projected into chart form." defaultOpen={false}>
          {isLive && hasSummaryData ? (
            <ChartContainer config={settingsChartConfig} className="min-h-[240px] w-full">
              <BarChart accessibilityLayer data={summaryChart}>
                <CartesianGrid vertical={false} strokeDasharray="2 4" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="count" fill="var(--color-count)" radius={6} />
              </BarChart>
            </ChartContainer>
          ) : isLive ? (
            <NoLiveDatapoints message="No queue summary points yet." />
          ) : (
            <LiveDataUnavailable />
          )}
        </CollapsibleCard>
      </div>
    </AppFrame>
  );
}
