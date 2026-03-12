import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    getQueueData: vi.fn().mockResolvedValue({
      data: {
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
      },
      source: { mode: "live" as const },
    }),
    getOverviewData: vi.fn().mockResolvedValue({
      data: {
        rows: [{ repo: "flow-healer", status: "blocked" }],
        activity: [],
        logs: { lines: [] },
      },
      source: { mode: "live" as const },
    }),
    getIssueDetailData: vi.fn().mockResolvedValue({
      data: {
        found: true,
        issue: { issue_id: "101" },
        repo: { policy: { summary: "Policy context is available for this issue." } },
        attempts: [{ attempt_id: "attempt-1", state: "failed", failure_reason: "Validation still failed." }],
        activity: [],
      },
      source: { mode: "live" as const },
    }),
  };
});

describe("OperationsWorkbench", () => {
  it("renders the redesigned operations shell with analytics surfaces", async () => {
    render(<OperationsWorkbench initialQueue={queue} initialOverview={overview} initialIssueId="101" />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /operations/i })).toBeInTheDocument();
      expect(screen.getByText(/queue analytics/i)).toBeInTheDocument();
      expect(screen.getByText(/state distribution/i)).toBeInTheDocument();
      expect(screen.getByText(/queue view counts/i)).toBeInTheDocument();
    });
  });

  it("opens issue detail in a modal when clicking an issue row", async () => {
    render(<OperationsWorkbench initialQueue={queue} initialOverview={overview} initialIssueId="101" />);

    const issueButton = await screen.findByRole("button", { name: /blocked issue/i });
    fireEvent.click(issueButton);

    await waitFor(() => {
      const dialog = screen.getByRole("dialog", { name: /selected issue detail/i });
      expect(within(dialog).getByText(/selected issue detail/i)).toBeInTheDocument();
    });
  });
});
