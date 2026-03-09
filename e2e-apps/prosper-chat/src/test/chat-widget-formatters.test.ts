import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatWidget from "@/components/chat/ChatWidget";

const SERVICES = [
  {
    id: "service-1",
    name: "Consultation",
    duration_minutes: 30,
    price_text: null,
  },
];

describe("ChatWidget formatters", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-28T20:00:00Z"));
    vi.stubGlobal("fetch", vi.fn());
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    cleanup();
  });

  it("formats single-digit appointment slots consistently", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ slots: ["09:05", "13:00"] }),
    } as Response);

    render(React.createElement(ChatWidget, { embedded: true, widgetToken: "widget-token", services: SERVICES }));

    fireEvent.click(screen.getByRole("button", { name: /book appointment/i }));
    fireEvent.click(screen.getByRole("button", { name: /consultation/i }));
    fireEvent.click(screen.getByRole("button", { name: "Sat, Feb 28" }));
    await vi.runAllTimersAsync();

    expect(screen.getByRole("button", { name: "9:05 AM" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1:00 PM" })).toBeInTheDocument();
  });

  it("keeps date labels stable across month and year boundaries", async () => {
    vi.setSystemTime(new Date("2026-12-31T20:00:00Z"));

    render(React.createElement(ChatWidget, { embedded: true, widgetToken: "widget-token", services: SERVICES }));

    fireEvent.click(screen.getByRole("button", { name: /book appointment/i }));
    fireEvent.click(screen.getByRole("button", { name: /consultation/i }));

    expect(screen.getByRole("button", { name: "Thu, Dec 31" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fri, Jan 1" })).toBeInTheDocument();
  });
});
