"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, Command, FolderKanban, MoonStar, Settings2, SunMedium } from "lucide-react";
import { useTheme } from "next-themes";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { DataSourceState } from "@/lib/flow-healer";

const navItems = [
  { href: "/operations", label: "Operations", icon: Command },
  { href: "/telemetry", label: "Telemetry", icon: Activity },
  { href: "/artifacts", label: "Artifacts", icon: FolderKanban },
  { href: "/settings", label: "Settings", icon: Settings2 },
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
    <div className="min-h-screen pb-20 lg:pb-0">
      <header className="sticky top-0 z-30 border-b border-border/80 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-[1600px] items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md border border-border/80 bg-card/90">
              <BarChart3 className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-semibold tracking-tight">Flow Healer</p>
              <p className="text-[11px] text-muted-foreground">AI Ops Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="hidden md:inline-flex">
              <Command className="h-4 w-4" />
              Cmd + K
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
              aria-label="Toggle theme"
            >
              {resolvedTheme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
            </Button>
            {actions}
          </div>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-[1600px] gap-4 px-4 py-4 sm:px-6 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="hidden space-y-4 lg:block">
          <Card className="p-3">
            <nav className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition hover:bg-secondary/70 hover:text-foreground",
                      currentPath.startsWith(item.href) && "bg-secondary text-foreground",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </Card>

          <Card className="p-4">
            <p className="eyebrow">Runtime</p>
            <h3 className="mt-2 text-sm font-semibold">Source mode</h3>
            <div className="mt-3 flex items-center gap-2">
              <Badge variant={source?.mode === "live" ? "success" : "warning"}>{source?.mode === "live" ? "Live" : "Fallback"}</Badge>
            </div>
            {source?.error && <p className="mt-3 text-xs text-muted-foreground">{source.error}</p>}
          </Card>
        </aside>

        <section className="space-y-4">
          <Card className="p-5">
            <p className="eyebrow">Control plane</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>
            <div className="mt-3 flex items-center gap-2 lg:hidden">
              <Badge variant={source?.mode === "live" ? "success" : "warning"}>{source?.mode === "live" ? "Live" : "Fallback"}</Badge>
              {source?.error && <span className="text-xs text-muted-foreground">{source.error}</span>}
            </div>
          </Card>
          {children}
        </section>
      </main>

      <nav className="fixed inset-x-3 bottom-3 z-40 lg:hidden">
        <Card className="p-2">
          <ul className="grid grid-cols-4 gap-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = currentPath.startsWith(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={cn(
                      "flex flex-col items-center justify-center gap-1 rounded-md px-2 py-2 text-[11px] font-medium text-muted-foreground transition",
                      active ? "bg-secondary text-foreground" : "hover:bg-secondary/70 hover:text-foreground",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
      </nav>
    </div>
  );
}
