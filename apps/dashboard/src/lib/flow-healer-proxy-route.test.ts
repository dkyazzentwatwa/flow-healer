import { NextRequest } from "next/server";

import { GET } from "../../app/api/flow-healer/[...path]/route";

describe("flow-healer proxy route", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("returns a gateway error response when backend connection fails", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("connect ECONNREFUSED 127.0.0.1:8788")) as typeof fetch;

    const request = new NextRequest("http://localhost:3000/api/flow-healer/api/queue");
    const response = await GET(request, { params: Promise.resolve({ path: ["api", "queue"] }) });
    const payload = await response.json();

    expect(response.status).toBe(502);
    expect(payload).toEqual(
      expect.objectContaining({
        error: "Flow Healer API unavailable",
      }),
    );
  });
});
