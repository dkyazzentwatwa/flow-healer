import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { OperationsWorkbench } from "@/components/dashboard/operations-workbench";

const queue = {
  rows: [
    {
      issue_id: "101",
      repo: "flow-healer",
      title: "Blocked issue",
      state: "blocked",
      explanation_summary: "Validation failed on the last attempt.",
      view_memberships: ["all", "blocked"],
    },
  ],
  views: [
    { id: "all", label: "All", count: 1 },
    { id: "blocked", label: "Blocked", count: 1 },
  ],
  summary: { total: 1, blocked: 1, running: 0, pr_open: 0, needs_review: 1 },
};

const overview = {
  rows: [{ repo: "flow-healer", status: "blocked" }],
  activity: [],
  logs: { lines: [] },
};

const issueDetail = {
  found: true,
  issue: { issue_id: "101" },
  repo: { policy: { summary: "Policy context is available for this issue." } },
  attempts: [{ attempt_id: "attempt-1", state: "failed", failure_reason: "Validation still failed." }],
  activity: [],
};

vi.mock("@/lib/flow-healer", async () => {
  const actual = await vi.importActual<typeof import("@/lib/flow-healer")>("@/lib/flow-healer");
  return {
    ...actual,
    getQueue: vi.fn().mockResolvedValue({
      rows: [
        {
          issue_id: "101",
          repo: "flow-healer",
          title: "Blocked issue",
          state: "blocked",
          explanation_summary: "Validation failed on the last attempt.",
          view_memberships: ["all", "blocked"],
        },
      ],
      views: [
        { id: "all", label: "All", count: 1 },
        { id: "blocked", label: "Blocked", count: 1 },
      ],
      summary: { total: 1, blocked: 1, running: 0, pr_open: 0, needs_review: 1 },
    }),
    getOverview: vi.fn().mockResolvedValue({
      rows: [{ repo: "flow-healer", status: "blocked" }],
      activity: [],
      logs: { lines: [] },
    }),
    getIssueDetail: vi.fn().mockResolvedValue({
      found: true,
      issue: { issue_id: "101" },
      repo: { policy: { summary: "Policy context is available for this issue." } },
      attempts: [{ attempt_id: "attempt-1", state: "failed", failure_reason: "Validation still failed." }],
      activity: [],
    }),
  };
});

describe("OperationsWorkbench", () => {
  it("renders the operations shell with collapsible inspector sections", async () => {
    render(<OperationsWorkbench initialQueue={queue} initialOverview={overview} initialIssueId="101" />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /operations/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^summary$/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^attempts$/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^validation$/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^artifacts$/i })).toBeInTheDocument();
    });
  });
});
