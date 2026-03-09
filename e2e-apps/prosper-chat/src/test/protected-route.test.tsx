import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProtectedRoute from "@/components/ProtectedRoute";

const mockUseAuth = vi.fn();
const mockUseQuery = vi.fn();

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

vi.mock("@/integrations/supabase/client", () => ({
  supabase: {},
}));

describe("ProtectedRoute", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseQuery.mockReset();
  });

  it("redirects unauthenticated visitors to auth even if the business query is still loading", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: false,
    });
    mockUseQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
    });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Protected content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/auth" element={<div>Auth screen</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Auth screen")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("shows the loading spinner while auth state is still resolving", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: true,
    });
    mockUseQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
    });

    const { container } = render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Protected content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/auth" element={<div>Auth screen</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(container.querySelector(".animate-spin")).toBeInTheDocument();
    expect(screen.queryByText("Auth screen")).not.toBeInTheDocument();
  });
});
