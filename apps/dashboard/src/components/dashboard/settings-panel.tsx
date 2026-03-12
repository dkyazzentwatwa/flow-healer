"use client";

import React from "react";
import { useEffect, useState } from "react";

import { AppFrame } from "@/components/dashboard/app-frame";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { getQueueData, type DataSourceState } from "@/lib/flow-healer";

export function SettingsPanel() {
  const [apiBaseUrl, setApiBaseUrl] = useState(process.env.NEXT_PUBLIC_FLOW_HEALER_API_BASE_URL || "http://127.0.0.1:8788");
  const [source, setSource] = useState<DataSourceState>({ mode: "fallback" });

  useEffect(() => {
    let active = true;
    void getQueueData().then((result) => {
      if (!active) return;
      setSource(result.source);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <AppFrame title="Settings" subtitle="Local dashboard preferences and connection details." source={source}>
      <div className="space-y-4">
        <Collapsible defaultOpen className="panel p-5">
          <CollapsibleTrigger className="w-full text-left">
            <div className="flex items-center justify-between">
              <div>
                <p className="eyebrow">Connection</p>
                <h2 className="text-lg font-semibold tracking-tight">Backend target</h2>
              </div>
              <Badge>Local</Badge>
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-4 space-y-3">
            <p className="text-sm text-muted-foreground">The Next app talks to Flow Healer through its JSON API server. Keep the UI separate, keep the backend focused.</p>
            <Input value={apiBaseUrl} onChange={(event) => setApiBaseUrl(event.target.value)} />
            <p className="text-xs text-muted-foreground">
              Set <code>FLOW_HEALER_API_BASE_URL</code> before <code>npm run dev</code> if your backend is not on port 8788.
            </p>
          </CollapsibleContent>
        </Collapsible>

        <Collapsible defaultOpen className="panel p-5">
          <CollapsibleTrigger className="w-full text-left">
            <div>
              <p className="eyebrow">Preferences</p>
              <h2 className="text-lg font-semibold tracking-tight">Personal shell state</h2>
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-4 text-sm text-muted-foreground">
            Collapse state, density, display mode, and theme should live here over time. This first cut keeps the panel structure ready for that without turning settings into a junk drawer.
          </CollapsibleContent>
        </Collapsible>
      </div>
    </AppFrame>
  );
}
