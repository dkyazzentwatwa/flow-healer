"use client";

import React from "react";
import { useEffect, useState } from "react";
import { ArrowUpRight, ImageIcon, ScrollText } from "lucide-react";

import { AppFrame } from "@/components/dashboard/app-frame";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getArtifactsData, type ArtifactEntry, type DataSourceState } from "@/lib/flow-healer";

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

  return (
    <AppFrame title="Artifacts" subtitle="Review evidence without leaving the shell." source={source}>
      <div className="grid gap-4 md:grid-cols-2">
        {!artifacts.length && (
          <article className="panel p-5 md:col-span-2">
            <p className="eyebrow">Artifacts</p>
            <h2 className="mt-2 text-lg font-semibold tracking-tight">No captured evidence yet</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              When Flow Healer records screenshots, transcripts, or other attempt evidence, it will appear here automatically.
            </p>
          </article>
        )}
        {artifacts.map((artifact) => (
          <article key={artifact.id} className="panel p-5">
            <div className="flex items-center justify-between">
              <Badge>{artifact.repo}</Badge>
              <Badge>{artifact.issue}</Badge>
            </div>
            <div className="mt-5 flex items-start gap-4">
              <div className="rounded-2xl bg-secondary p-3">
                {artifact.kind === "image" ? <ImageIcon className="h-5 w-5" /> : <ScrollText className="h-5 w-5" />}
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">{artifact.label}</h2>
                <p className="mt-2 text-sm text-muted-foreground">Artifacts stay as a separate browseable surface instead of cluttering the main workbench.</p>
              </div>
            </div>
            <div className="mt-6">
              <Button asChild>
                <a href={artifact.href} target="_blank" rel="noreferrer">
                  Open artifact
                  <ArrowUpRight className="h-4 w-4" />
                </a>
              </Button>
            </div>
          </article>
        ))}
      </div>
    </AppFrame>
  );
}
