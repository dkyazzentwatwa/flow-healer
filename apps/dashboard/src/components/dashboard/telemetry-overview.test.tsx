import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { TelemetryOverview } from "@/components/dashboard/telemetry-overview";

const { mockedGetOverviewData } = vi.hoisted(() => ({
  mockedGetOverviewData: vi.fn(),
}));

vi.mock("@/lib/flow-healer", async () => {
  const actual = await vi.importActual<typeof import("@/lib/flow-healer")>("@/lib/flow-healer");
  return {
    ...actual,
    getOverviewData: mockedGetOverviewData,
  };
});

describe("TelemetryOverview", () => {
  beforeEach(() => {
    mockedGetOverviewData.mockReset();
    mockedGetOverviewData.mockResolvedValue({
      data: {
        rows: [{ repo: "flow-healer", status: "blocked" }],
        activity: [{ id: "1", signal: "failure", summary: "Issue #101 failed" }],
        logs: { lines: ["sample line"] },
        scoreboard: { first_pass_success_rate: 0.66, issue_successes: 12, issue_failures: 6 },
        chart_series: {
          reliability: [
            { day: "Mon", first_pass_success_rate: 0.5 },
            { day: "Tue", first_pass_success_rate: 0.66 },
          ],
        },
      },
      source: { mode: "live" as const },
    });
  });

  it("renders telemetry analytics cards and chart sections", async () => {
    render(<TelemetryOverview />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: /^Telemetry$/i })).toBeInTheDocument();
      expect(screen.getByText(/reliability analytics/i)).toBeInTheDocument();
      expect(screen.getByText(/success vs failures/i)).toBeInTheDocument();
      expect(screen.getByText(/activity signal/i)).toBeInTheDocument();
    });
  });

  it("hides chart data when telemetry source is fallback", async () => {
    mockedGetOverviewData.mockResolvedValueOnce({
      data: {
        rows: [],
        activity: [],
        logs: { lines: [] },
        scoreboard: {},
        chart_series: { reliability: [] },
      },
      source: { mode: "fallback" as const, error: "offline" },
    });

    render(<TelemetryOverview />);

    await waitFor(() => {
      expect(screen.getAllByText(/live data unavailable/i).length).toBeGreaterThan(0);
    });
  });
});
