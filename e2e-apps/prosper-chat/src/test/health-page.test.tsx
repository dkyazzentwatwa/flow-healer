import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Health from "@/pages/Health";

describe("Health page", () => {
  it("surfaces a production-shaped operational status message", () => {
    render(<Health />);

    expect(
      screen.getByRole("region", { name: "Application health status" }),
    ).toBeInTheDocument();
    expect(screen.getByText("System status")).toBeInTheDocument();
    expect(screen.getByText("Operational")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Prosper Chat is accepting requests and core services are responding normally.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^ok$/i)).not.toBeInTheDocument();
  });
});
