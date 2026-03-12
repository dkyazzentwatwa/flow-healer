"use client";

import React from "react";
import { ChevronDown } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

type CollapsibleCardProps = {
  title: React.ReactNode;
  description?: React.ReactNode;
  defaultOpen?: boolean;
  headerRight?: React.ReactNode;
  className?: string;
  contentClassName?: string;
  children: React.ReactNode;
};

export function CollapsibleCard({
  title,
  description,
  defaultOpen = true,
  headerRight,
  className,
  contentClassName,
  children,
}: CollapsibleCardProps) {
  const [open, setOpen] = React.useState(defaultOpen);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className={className}>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>{title}</CardTitle>
              {description ? <CardDescription className="mt-1">{description}</CardDescription> : null}
            </div>
            <div className="flex items-center gap-2">
              {headerRight}
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border/70 bg-background/50 text-muted-foreground transition hover:bg-secondary/70 hover:text-foreground"
                  aria-label={open ? "Collapse section" : "Expand section"}
                >
                  <ChevronDown className={cn("h-4 w-4 transition", open ? "rotate-180" : "rotate-0")} />
                </button>
              </CollapsibleTrigger>
            </div>
          </div>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className={contentClassName}>{children}</CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
