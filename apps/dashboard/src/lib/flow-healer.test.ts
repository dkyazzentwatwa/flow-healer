import {
  extractArtifactsFromIssueDetail,
  getArtifactsData,
  getQueueData,
  normalizeArtifactHref,
} from "@/lib/flow-healer";

describe("flow-healer data client", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("reports fallback mode when queue fetch fails", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("backend down")) as typeof fetch;

    const result = await getQueueData();

    expect(result.source.mode).toBe("fallback");
    expect(result.source.error).toMatch(/backend down/i);
    expect(result.data.rows.length).toBeGreaterThan(0);
  });

  it("normalizes backend artifact hrefs through the Next proxy", () => {
    expect(normalizeArtifactHref("/artifact?path=%2Ftmp%2Fone.png")).toBe("/api/flow-healer/artifact?path=%2Ftmp%2Fone.png");
    expect(normalizeArtifactHref("/api/flow-healer/artifact?path=%2Ftmp%2Fone.png")).toBe("/api/flow-healer/artifact?path=%2Ftmp%2Fone.png");
  });

  it("extracts artifacts from issue detail attempts", () => {
    const artifacts = extractArtifactsFromIssueDetail(
      {
        attempts: [
          {
            attempt_id: "ha_910_1",
            artifact_links: [
              {
                label: "failure_screenshot",
                target: "/tmp/failure.png",
                web_href: "/artifact?path=%2Ftmp%2Ffailure.png",
              },
            ],
          },
        ],
      },
      { repo: "demo", issueId: "910" },
    );

    expect(artifacts).toEqual([
      expect.objectContaining({
        repo: "demo",
        issue: "910",
        kind: "image",
        href: "/api/flow-healer/artifact?path=%2Ftmp%2Ffailure.png",
      }),
    ]);
  });

  it("aggregates live artifacts from queue and issue detail responses", async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const href = String(input);
      if (href.includes("/api/flow-healer/api/queue")) {
        return new Response(
          JSON.stringify({
            rows: [{ issue_id: "910", repo: "demo", title: "Blocked issue", state: "blocked" }],
            views: [],
            summary: { total: 1 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (href.includes("/api/flow-healer/api/issue-detail")) {
        return new Response(
          JSON.stringify({
            found: true,
            attempts: [
              {
                attempt_id: "ha_910_1",
                artifact_links: [
                  {
                    label: "failure_screenshot",
                    target: "/tmp/failure.png",
                    web_href: "/artifact?path=%2Ftmp%2Ffailure.png",
                  },
                ],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`Unexpected request: ${href}`);
    }) as typeof fetch;

    const result = await getArtifactsData();

    expect(result.source.mode).toBe("live");
    expect(result.data).toEqual([
      expect.objectContaining({
        repo: "demo",
        issue: "910",
        href: "/api/flow-healer/artifact?path=%2Ftmp%2Ffailure.png",
      }),
    ]);
  });
});
