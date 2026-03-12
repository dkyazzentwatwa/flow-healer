"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MoonStar, PanelLeft, Search, SunMedium } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DataSourceState } from "@/lib/flow-healer";

const navItems = [
  { href: "/operations", label: "Operations" },
  { href: "/telemetry", label: "Telemetry" },
  { href: "/artifacts", label: "Artifacts" },
  { href: "/settings", label: "Settings" },
];

export function AppFrame({
  title,
  subtitle,
  actions,
  source,
  children,
}: {
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
  source?: DataSourceState;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const currentPath = pathname || "";
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="mx-auto grid min-h-[calc(100vh-2rem)] max-w-[1600px] grid-cols-1 gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="panel hidden flex-col p-4 lg:flex">
          <div className="mb-6 flex items-center gap-3">
            <div className="rounded-xl bg-primary/15 p-2 text-primary">
              <PanelLeft className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-semibold tracking-tight">Flow Healer</p>
              <p className="text-xs text-muted-foreground">Dashboard</p>
            </div>
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center rounded-xl px-3 py-2 text-sm text-muted-foreground transition hover:bg-secondary hover:text-foreground",
                  currentPath.startsWith(item.href) && "bg-secondary text-foreground",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="mt-auto rounded-2xl border bg-secondary/40 p-4">
            <p className="eyebrow">Runtime</p>
            <h3 className="mt-2 font-medium tracking-tight">Separate app shell</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Run this app with <code>npm run dev</code> and keep Flow Healer focused on data and automation.
            </p>
          </div>
        </aside>

        <div className="space-y-4">
          <header className="panel flex items-center justify-between gap-4 px-5 py-4">
            <div>
              <p className="eyebrow">Operations shell</p>
              <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{title}</h1>
              <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
              {source && (
                <div className="mt-3 flex items-center gap-2">
                  <Badge variant={source.mode === "live" ? "success" : "warning"}>
                    {source.mode === "live" ? "Live backend" : "Fallback data"}
                  </Badge>
                  {source.error && <span className="text-xs text-muted-foreground">{source.error}</span>}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="icon">
                <Search className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
              >
                {resolvedTheme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
              </Button>
              {actions}
            </div>
          </header>
          {children}
        </div>
      </div>
    </div>
  );
}
