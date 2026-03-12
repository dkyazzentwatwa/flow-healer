"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Pie, PieChart, Cell, XAxis, YAxis } from "recharts";

import { AppFrame } from "@/components/dashboard/app-frame";
import { CollapsibleCard } from "@/components/dashboard/collapsible-card";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ChartContainer, type ChartConfig, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { getOverviewData, type DataSourceState, type OverviewPayload } from "@/lib/flow-healer";

const reliabilityConfig = {
  success: { label: "Reliability %", color: "hsl(0 0% 96%)" },
} satisfies ChartConfig;

const scoreboardConfig = {
  successes: { label: "Successes", color: "hsl(0 0% 92%)" },
  failures: { label: "Failures", color: "hsl(0 0% 65%)" },
} satisfies ChartConfig;

const activityConfig = {
  count: { label: "Events", color: "hsl(0 0% 88%)" },
} satisfies ChartConfig;

const pieColors = ["hsl(0 0% 96%)", "hsl(0 0% 82%)", "hsl(0 0% 68%)", "hsl(0 0% 52%)"];

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

  const isLive = source.mode === "live";

  const reliability = useMemo(
    () =>
      (overview.chart_series?.reliability || []).map((entry, index) => ({
        day: String(entry.day || `S${index + 1}`),
        success: Math.round(Number(entry.first_pass_success_rate || 0) * 100),
      })),
    [overview.chart_series?.reliability],
  );

  const scoreboard = useMemo(() => {
    const raw = overview.scoreboard || {};
    const hasScoreboardValues = "issue_successes" in raw || "issue_failures" in raw;
    return [
      { label: "successes", successes: Number(raw.issue_successes || 0), failures: 0, hasScoreboardValues },
      { label: "failures", successes: 0, failures: Number(raw.issue_failures || 0), hasScoreboardValues },
    ];
  }, [overview.scoreboard]);

  const activitySignals = useMemo(() => {
    const counts = new Map<string, number>();
    (overview.activity || []).forEach((item) => {
      const signal = String(item.signal || "unknown");
      counts.set(signal, (counts.get(signal) || 0) + 1);
    });
    return [...counts.entries()].map(([signal, count]) => ({ signal, count }));
  }, [overview.activity]);

  const kpiCards = [
    { label: "Repos observed", value: overview.rows.length },
    { label: "Successes", value: Number(overview.scoreboard?.issue_successes || 0) },
    { label: "Failures", value: Number(overview.scoreboard?.issue_failures || 0) },
    {
      label: "First pass rate",
      value: `${Math.round(Number(overview.scoreboard?.first_pass_success_rate || 0) * 100)}%`,
    },
  ];
  const hasReliability = reliability.length > 0;
  const hasScoreboardData = scoreboard.some((entry) => entry.hasScoreboardValues);
  const hasActivitySignals = activitySignals.length > 0;

  return (
    <AppFrame title="Telemetry" subtitle="Mobile-first analytics cockpit with consistent collapsible surfaces and real-data charting." source={source}>
      <CollapsibleCard title="Telemetry KPIs" description="Live runtime metrics" defaultOpen>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {kpiCards.map((metric) => (
            <Card key={metric.label} className="bg-card/85 p-4">
              <p className="text-xs text-muted-foreground">{metric.label}</p>
              <p className="metric-value mt-1">{isLive ? metric.value : "—"}</p>
            </Card>
          ))}
        </div>
      </CollapsibleCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <CollapsibleCard title="Reliability analytics" description="First-pass success trend by day" defaultOpen>
          {isLive && hasReliability ? (
            <ChartContainer config={reliabilityConfig} className="min-h-[260px] w-full">
              <AreaChart accessibilityLayer data={reliability}>
                <CartesianGrid vertical={false} strokeDasharray="2 4" />
                <XAxis dataKey="day" tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Area dataKey="success" type="monotone" stroke="var(--color-success)" fill="var(--color-success)" fillOpacity={0.24} />
              </AreaChart>
            </ChartContainer>
          ) : isLive ? (
            <NoLiveDatapoints message="No reliability trend points yet." />
          ) : (
            <LiveDataUnavailable />
          )}
        </CollapsibleCard>

        <CollapsibleCard title="Success vs failures" description="Scoreboard comparison from live overview metrics" defaultOpen>
          {isLive && hasScoreboardData ? (
            <ChartContainer config={scoreboardConfig} className="min-h-[260px] w-full">
              <BarChart accessibilityLayer data={scoreboard}>
                <CartesianGrid vertical={false} strokeDasharray="2 4" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="successes" fill="var(--color-successes)" radius={6} />
                <Bar dataKey="failures" fill="var(--color-failures)" radius={6} />
              </BarChart>
            </ChartContainer>
          ) : isLive ? (
            <NoLiveDatapoints message="No success/failure scoreboard points yet." />
          ) : (
            <LiveDataUnavailable />
          )}
        </CollapsibleCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <CollapsibleCard title="Activity signal" description="Signal composition across recent events" defaultOpen={false}>
          {isLive && hasActivitySignals ? (
            <ChartContainer config={activityConfig} className="min-h-[250px] w-full">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Pie
                  data={activitySignals}
                  dataKey="count"
                  nameKey="signal"
                  innerRadius={48}
                  outerRadius={84}
                  stroke="none"
                >
                  {activitySignals.map((entry, index) => (
                    <Cell key={entry.signal} fill={pieColors[index % pieColors.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
          ) : isLive ? (
            <NoLiveDatapoints message="No activity-signal points yet." />
          ) : (
            <LiveDataUnavailable />
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {activitySignals.map((entry) => (
              <Badge key={entry.signal} variant="default">
                {entry.signal}: {entry.count}
              </Badge>
            ))}
            {!hasActivitySignals && <p className="text-xs text-muted-foreground">No activity signals detected yet.</p>}
          </div>
        </CollapsibleCard>

        <CollapsibleCard title="Recent output" description="Latest runtime logs and repo health summaries" defaultOpen={false}>
          <div className="space-y-3">
            {(overview.rows || []).map((row, index) => (
              <div key={index} className="rounded-md border border-border/70 bg-background/40 p-3">
                <p className="text-sm font-semibold">{String(row.repo || "flow-healer")}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {String((row.trust as { summary?: string })?.summary || (row.policy as { summary?: string })?.summary || "No runtime summary.")}
                </p>
              </div>
            ))}
            {(overview.logs?.lines || []).slice(0, 6).map((line, index) => (
              <pre key={index} className="overflow-auto rounded-md border border-border/70 bg-background/40 p-3 font-mono text-[11px] text-muted-foreground">
                {line}
              </pre>
            ))}
          </div>
        </CollapsibleCard>
      </div>
    </AppFrame>
  );
}
