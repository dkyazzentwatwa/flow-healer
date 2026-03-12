"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, ImageIcon, ScrollText } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis } from "recharts";

import { AppFrame } from "@/components/dashboard/app-frame";
import { CollapsibleCard } from "@/components/dashboard/collapsible-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ChartContainer, type ChartConfig, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { getArtifactsData, type ArtifactEntry, type DataSourceState } from "@/lib/flow-healer";

const artifactConfig = {
  count: { label: "Artifacts", color: "hsl(0 0% 92%)" },
} satisfies ChartConfig;

const pieColors = ["hsl(0 0% 96%)", "hsl(0 0% 80%)", "hsl(0 0% 62%)", "hsl(0 0% 45%)"];

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

export function ArtifactBrowser() {
  const [artifacts, setArtifacts] = useState<ArtifactEntry[]>([]);
  const [source, setSource] = useState<DataSourceState>({ mode: "fallback" });

  useEffect(() => {
    let active = true;

    const refresh = async () => {
      const result = await getArtifactsData();
      if (!active) return;
      setArtifacts(result.data);
      setSource(result.source);
    };

    void refresh();

    return () => {
      active = false;
    };
  }, []);

  const isLive = source.mode === "live";

  const artifactsByRepo = useMemo(() => {
    const counts = new Map<string, number>();
    artifacts.forEach((artifact) => counts.set(artifact.repo, (counts.get(artifact.repo) || 0) + 1));
    return [...counts.entries()].map(([repo, count]) => ({ repo, count }));
  }, [artifacts]);

  const artifactsByKind = useMemo(() => {
    const counts = new Map<string, number>();
    artifacts.forEach((artifact) => counts.set(artifact.kind, (counts.get(artifact.kind) || 0) + 1));
    return [...counts.entries()].map(([kind, count]) => ({ kind, count }));
  }, [artifacts]);
  const hasArtifactsByRepo = artifactsByRepo.length > 0;
  const hasArtifactsByKind = artifactsByKind.length > 0;

  return (
    <AppFrame title="Artifacts" subtitle="Mobile-first evidence explorer with collapsible sections and live-data chart rules." source={source}>
      <div className="grid gap-4 xl:grid-cols-2">
        <CollapsibleCard title="Artifacts by repository" description="Where evidence volume is accumulating" defaultOpen>
          {isLive && hasArtifactsByRepo ? (
            <ChartContainer config={artifactConfig} className="min-h-[240px] w-full">
              <BarChart accessibilityLayer data={artifactsByRepo}>
                <CartesianGrid vertical={false} strokeDasharray="2 4" />
                <XAxis dataKey="repo" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="count" fill="var(--color-count)" radius={6} />
              </BarChart>
            </ChartContainer>
          ) : isLive ? (
            <NoLiveDatapoints message="No repository artifact counts yet." />
          ) : (
            <LiveDataUnavailable />
          )}
        </CollapsibleCard>

        <CollapsibleCard title="Artifact type mix" description="Image vs text evidence composition" defaultOpen>
          {isLive && hasArtifactsByKind ? (
            <ChartContainer config={artifactConfig} className="min-h-[240px] w-full">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Pie
                  data={artifactsByKind}
                  dataKey="count"
                  nameKey="kind"
                  innerRadius={44}
                  outerRadius={82}
                  stroke="none"
                >
                  {artifactsByKind.map((entry, index) => (
                    <Cell key={entry.kind} fill={pieColors[index % pieColors.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
          ) : isLive ? (
            <NoLiveDatapoints message="No artifact-type composition points yet." />
          ) : (
            <LiveDataUnavailable />
          )}
        </CollapsibleCard>
      </div>

      <CollapsibleCard title="Artifact list" description="Per-artifact details and outbound links" defaultOpen={false}>
        <div className="grid gap-4 md:grid-cols-2">
          {!artifacts.length && (
            <Card className="md:col-span-2 p-5">
              <h3 className="text-sm font-semibold tracking-tight">No captured evidence yet</h3>
              <p className="mt-2 text-sm text-muted-foreground">When Flow Healer records screenshots or transcripts, they appear here automatically.</p>
            </Card>
          )}

          {artifacts.map((artifact) => (
            <Card key={artifact.id} className="p-5">
              <div className="flex items-center justify-between">
                <Badge>{artifact.repo}</Badge>
                <Badge>{artifact.issue}</Badge>
              </div>
              <h3 className="pt-3 text-sm font-semibold tracking-tight">{artifact.label}</h3>
              <p className="text-xs text-muted-foreground">{artifact.kind === "image" ? "Image evidence" : "Transcript evidence"}</p>

              <div className="mt-4 flex items-center gap-3 rounded-md border border-border/70 bg-background/40 p-3">
                <div className="rounded-md border border-border/70 bg-card/80 p-2">
                  {artifact.kind === "image" ? <ImageIcon className="h-5 w-5" /> : <ScrollText className="h-5 w-5" />}
                </div>
                <p className="text-sm text-muted-foreground">Artifact evidence is linked directly from issue attempts for faster reviews.</p>
              </div>
              <div className="mt-4">
                <Button asChild>
                  <a href={artifact.href} target="_blank" rel="noreferrer">
                    Open artifact
                    <ArrowUpRight className="h-4 w-4" />
                  </a>
                </Button>
              </div>
            </Card>
          ))}
        </div>
      </CollapsibleCard>
    </AppFrame>
  );
}
