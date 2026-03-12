import React from "react";
import * as ReactNamespace from "react";

import { cn } from "@/lib/utils";

export const Input = ReactNamespace.forwardRef<HTMLInputElement, ReactNamespace.ComponentProps<"input">>(({ className, ...props }, ref) => {
  return (
    <input
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-xl border bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...props}
    />
  );
});
Input.displayName = "Input";
