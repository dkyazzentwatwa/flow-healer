import { NextRequest } from "next/server";

const DEFAULT_BASE_URL = "http://127.0.0.1:8788";

function backendBaseUrl() {
  return (process.env.FLOW_HEALER_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");
}

async function proxy(request: NextRequest, path: string[]) {
  const url = new URL(`${backendBaseUrl()}/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.append(key, value));

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: request.method,
      headers: {
        Accept: request.headers.get("accept") || "*/*",
        "Content-Type": request.headers.get("content-type") || "",
      },
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return Response.json(
      {
        error: "Flow Healer API unavailable",
        detail: message,
      },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  return new Response(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/octet-stream",
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return proxy(request, path);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return proxy(request, path);
}
