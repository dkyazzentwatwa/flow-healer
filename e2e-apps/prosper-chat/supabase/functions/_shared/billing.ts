import { buildCorsHeaders, isOriginAllowed } from "./cors.ts";

export function getBillingCorsHeaders(req: Request): Record<string, string> {
  return buildCorsHeaders(req, "null");
}

export function ensureBillingOrigin(req: Request): { ok: boolean; corsHeaders: Record<string, string> } {
  const corsHeaders = getBillingCorsHeaders(req);
  return { ok: isOriginAllowed(req), corsHeaders };
}

export function getAppBaseUrl(req: Request): string {
  const configured = Deno.env.get("APP_BASE_URL");
  if (configured) return configured;

  const origin = req.headers.get("origin");
  if (origin && isOriginAllowed(req)) return origin;

  return "http://localhost:3000";
}
