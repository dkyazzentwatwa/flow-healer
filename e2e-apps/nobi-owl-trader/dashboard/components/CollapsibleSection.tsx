"use client";

import { PropsWithChildren, ReactNode, useId, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface CollapsibleSectionProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  defaultOpen?: boolean;
  headerRight?: ReactNode;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
}

export function CollapsibleSection({
  title,
  description,
  icon,
  defaultOpen = true,
  headerRight,
  className,
  headerClassName,
  bodyClassName,
  children,
}: PropsWithChildren<CollapsibleSectionProps>) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <div className={cn("card", className)}>
      <div className={cn("flex items-center justify-between", headerClassName)}>
        <div className="flex items-center gap-2">
          {icon}
          <div>
            <h3 className="text-sm font-semibold text-zinc-200">{title}</h3>
            {description && (
              <p className="text-xs text-zinc-500">{description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {headerRight}
          <button
            type="button"
            aria-expanded={isOpen}
            aria-controls={contentId}
            onClick={() => setIsOpen((prev) => !prev)}
            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 transition-colors"
          >
            {isOpen ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
      {isOpen && (
        <div id={contentId} className={bodyClassName}>
          {children}
        </div>
      )}
    </div>
  );
}
