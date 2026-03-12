"use client";

import React from "react";
import * as RechartsPrimitive from "recharts";

import { cn } from "@/lib/utils";

export type ChartConfig = {
  [key: string]: {
    label?: React.ReactNode;
    color?: string;
  };
};

type ChartContextValue = {
  config: ChartConfig;
};

const ChartContext = React.createContext<ChartContextValue | null>(null);

function useChart() {
  const context = React.useContext(ChartContext);
  if (!context) {
    throw new Error("useChart must be used inside a <ChartContainer />");
  }
  return context;
}

export const ChartContainer = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    config: ChartConfig;
    children: React.ComponentProps<typeof RechartsPrimitive.ResponsiveContainer>["children"];
  }
>(({ id, className, config, children, ...props }, ref) => {
  const uniqueId = React.useId().replace(/:/g, "");
  const chartId = `chart-${id || uniqueId}`;
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        ref={ref}
        className={cn(
          "h-[240px] w-full text-xs [&_.recharts-cartesian-grid_line[stroke='#ccc']]:stroke-border/70 [&_.recharts-dot[stroke='#fff']]:stroke-transparent [&_.recharts-polar-grid_[stroke='#ccc']]:stroke-border [&_.recharts-reference-line_[stroke='#ccc']]:stroke-border [&_.recharts-sector[stroke='#fff']]:stroke-transparent [&_.recharts-text.recharts-cartesian-axis-tick-value]:fill-muted-foreground",
          className,
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        {mounted ? (
          <RechartsPrimitive.ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={220}>
            {children}
          </RechartsPrimitive.ResponsiveContainer>
        ) : (
          <div className="h-full w-full" />
        )}
      </div>
    </ChartContext.Provider>
  );
});
ChartContainer.displayName = "ChartContainer";

const ChartStyle = ({ id, config }: { id: string; config: ChartConfig }) => {
  const colorConfig = Object.entries(config).filter(([, item]) => item.color);

  if (!colorConfig.length) {
    return null;
  }

  return (
    <style
      dangerouslySetInnerHTML={{
        __html: `
[data-chart=${id}] {
${colorConfig.map(([key, item]) => `  --color-${key}: ${item.color};`).join("\n")}
}
.dark [data-chart=${id}] {
${colorConfig.map(([key, item]) => `  --color-${key}: ${item.color};`).join("\n")}
}
`,
      }}
    />
  );
};

export function ChartTooltip(props: React.ComponentProps<typeof RechartsPrimitive.Tooltip>) {
  return <RechartsPrimitive.Tooltip cursor={false} isAnimationActive={false} {...props} />;
}

export function ChartTooltipContent({
  active,
  payload,
  hideLabel = false,
}: {
  active?: boolean;
  payload?: Array<{
    color?: string;
    dataKey?: string | number;
    value?: number | string;
    payload?: Record<string, unknown>;
  }>;
  hideLabel?: boolean;
}) {
  const { config } = useChart();

  if (!active || !payload?.length) {
    return null;
  }

  const dayValue = (payload[0]?.payload as Record<string, unknown> | undefined)?.day;
  const dayLabel = dayValue == null ? null : String(dayValue);

  return (
    <div className="grid min-w-[180px] gap-1 rounded-lg border border-border/80 bg-popover/95 px-3 py-2 text-xs text-popover-foreground shadow-xl">
      {!hideLabel && dayLabel && <div className="text-[11px] text-muted-foreground">{dayLabel}</div>}
      {payload.map((entry) => {
        const key = String(entry.dataKey || "value");
        const label = config[key]?.label ?? key;
        const color = entry.color || `var(--color-${key})`;

        return (
          <div key={key} className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full" style={{ background: color }} />
              <span className="text-muted-foreground">{label}</span>
            </div>
            <span className="font-medium text-foreground">{Number(entry.value || 0).toLocaleString()}</span>
          </div>
        );
      })}
    </div>
  );
}

export const ChartLegend = RechartsPrimitive.Legend;

export function ChartLegendContent({
  payload,
}: {
  payload?: Array<{ color?: string; dataKey?: string | number }>;
}) {
  const { config } = useChart();

  if (!payload?.length) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {payload.map((entry) => {
        const key = String(entry.dataKey || "value");
        const label = config[key]?.label ?? key;
        return (
          <div key={key} className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
            <span>{label}</span>
          </div>
        );
      })}
    </div>
  );
}
