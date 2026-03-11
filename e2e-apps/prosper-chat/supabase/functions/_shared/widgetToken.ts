export interface WidgetClaims {
  business_id: string;
  bot_id?: string;
  widget_key: string;
  exp: number;
}

type WidgetTokenInput = Record<string, unknown> | null | undefined;

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function normalizeOptionalWidgetField(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function getOptionalClaimValue(source: WidgetTokenInput, camelKey: string, snakeKey: string): string | null {
  if (!source) {
    return null;
  }

  return normalizeOptionalWidgetField(source[camelKey]) ?? normalizeOptionalWidgetField(source[snakeKey]);
}

export function extractWidgetToken(source: unknown): string | null {
  if (typeof source === "string") {
    return normalizeOptionalWidgetField(source);
  }

  if (!source || typeof source !== "object") {
    return null;
  }

  return getOptionalClaimValue(source as WidgetTokenInput, "widgetToken", "widget_token");
}

export function assertWidgetTokenMatchesContext(claims: WidgetClaims, source: unknown): void {
  if (!source || typeof source !== "object") {
    return;
  }

  const context = source as WidgetTokenInput;
  const widgetKey = getOptionalClaimValue(context, "widgetKey", "widget_key");
  if (widgetKey && widgetKey !== claims.widget_key) {
    throw new Error("Widget token does not match widget key");
  }

  const businessId = getOptionalClaimValue(context, "businessId", "business_id") ?? getOptionalClaimValue(context, "id", "id");
  if (businessId && businessId !== claims.business_id) {
    throw new Error("Widget token does not match business");
  }

  const botId = getOptionalClaimValue(context, "botId", "bot_id");
  if (botId && botId !== (claims.bot_id ?? null)) {
    throw new Error("Widget token does not match bot");
  }
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromBase64Url(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function getKey(): Promise<CryptoKey> {
  const secret = Deno.env.get("WIDGET_TOKEN_SECRET");
  if (!secret) {
    throw new Error("WIDGET_TOKEN_SECRET is not configured");
  }
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export async function signWidgetToken(claims: WidgetClaims): Promise<string> {
  const payload = toBase64Url(encoder.encode(JSON.stringify(claims)));
  const key = await getKey();
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(payload)));
  return `${payload}.${toBase64Url(signature)}`;
}

export async function verifyWidgetToken(token: string): Promise<WidgetClaims> {
  const [payload, signature] = token.split(".");
  if (!payload || !signature) {
    throw new Error("Invalid widget token format");
  }

  const key = await getKey();
  const isValid = await crypto.subtle.verify(
    "HMAC",
    key,
    fromBase64Url(signature),
    encoder.encode(payload),
  );
  if (!isValid) {
    throw new Error("Invalid widget token signature");
  }

  let claims: WidgetClaims;
  try {
    claims = JSON.parse(decoder.decode(fromBase64Url(payload))) as WidgetClaims;
  } catch {
    throw new Error("Invalid widget token payload");
  }

  if (!claims.business_id || !claims.widget_key || !claims.exp) {
    throw new Error("Widget token claims are incomplete");
  }

  const now = Math.floor(Date.now() / 1000);
  if (claims.exp < now) {
    throw new Error("Widget token has expired");
  }

  return claims;
}
