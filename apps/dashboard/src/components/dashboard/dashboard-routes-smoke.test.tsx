import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { ArtifactBrowser } from "@/components/dashboard/artifact-browser";
import { SettingsPanel } from "@/components/dashboard/settings-panel";

vi.mock("@/lib/flow-healer", async () => {
  const actual = await vi.importActual<typeof import("@/lib/flow-healer")>("@/lib/flow-healer");
  return {
    ...actual,
    getArtifactsData: vi.fn().mockResolvedValue({
      data: [
        {
          id: "artifact-1",
          label: "Failure screenshot",
          kind: "image",
          repo: "flow-healer",
          issue: "101",
          href: "/tmp/artifact.png",
        },
      ],
      source: { mode: "live" },
    }),
    getQueueData: vi.fn().mockResolvedValue({
      data: {
        rows: [],
        views: [],
        summary: { total: 3, running: 1, blocked: 1, pr_open: 1, needs_review: 1 },
      },
      source: { mode: "live" },
    }),
  };
});

describe("Dashboard route smoke", () => {
  it("renders artifacts analytics surface", async () => {
    render(<ArtifactBrowser />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: /^artifacts$/i })).toBeInTheDocument();
      expect(screen.getByText(/artifacts by repository/i)).toBeInTheDocument();
      expect(screen.getByText(/artifact type mix/i)).toBeInTheDocument();
    });
  });

  it("renders settings analytics surface", async () => {
    render(<SettingsPanel />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: /^settings$/i })).toBeInTheDocument();
      expect(screen.getByText(/backend target/i)).toBeInTheDocument();
      expect(screen.getByText(/queue snapshot/i)).toBeInTheDocument();
    });
  });
});
