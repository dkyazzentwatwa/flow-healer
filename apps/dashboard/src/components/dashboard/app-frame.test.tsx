import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { vi } from "vitest";

import { AppFrame } from "@/components/dashboard/app-frame";

const setTheme = vi.fn();
let mockResolvedTheme: string | undefined = "dark";

vi.mock("next/navigation", () => ({
  usePathname: () => "/operations",
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({
    resolvedTheme: mockResolvedTheme,
    setTheme,
  }),
}));

describe("AppFrame theme toggle", () => {
  beforeEach(() => {
    mockResolvedTheme = "dark";
    setTheme.mockReset();
  });

  it("renders a hydration-safe pending icon during server render", () => {
    const html = renderToString(
      <AppFrame title="Operations" subtitle="Subtitle">
        <div>content</div>
      </AppFrame>,
    );

    expect(html).toContain('data-theme-icon="pending"');
  });

  it("renders the resolved icon after client mount", async () => {
    render(
      <AppFrame title="Operations" subtitle="Subtitle">
        <div>content</div>
      </AppFrame>,
    );

    const toggle = screen.getByRole("button", { name: /toggle theme/i });
    await waitFor(() => {
      expect(toggle.querySelector('[data-theme-icon="sun"]')).toBeInTheDocument();
    });
  });
});
