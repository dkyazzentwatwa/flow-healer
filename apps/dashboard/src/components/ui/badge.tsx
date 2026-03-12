import React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center rounded-md border border-border/70 px-2 py-1 text-[11px] font-medium tracking-wide", {
  variants: {
    variant: {
      default: "bg-secondary/80 text-secondary-foreground",
      success: "bg-emerald-500/10 text-emerald-400",
      warning: "bg-amber-500/10 text-amber-400",
      danger: "bg-rose-500/10 text-rose-400",
      info: "bg-sky-500/10 text-sky-400",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

export function Badge({ className, variant, ...props }: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof badgeVariants>) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
