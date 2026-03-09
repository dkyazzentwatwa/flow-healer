import { buildCorsHeaders, isOriginAllowed } from "./cors.ts";

const BILLING_PLANS = ["free", "pro", "agency"] as const;
const BILLING_STATUSES = ["active", "cancelled", "past_due"] as const;

export type BillingPlan = (typeof BILLING_PLANS)[number];
export type BillingStatus = (typeof BILLING_STATUSES)[number];

export type ExistingSubscription = {
  plan?: string | null;
  status?: string | null;
  stripe_subscription_id?: string | null;
  current_period_start?: string | null;
  current_period_end?: string | null;
};

type StripeSubscriptionLike = {
  id?: string | null;
  status?: string | null;
  current_period_start?: number | null;
  current_period_end?: number | null;
};

export type NormalizedSubscription = {
  subscribed: boolean;
  plan: BillingPlan;
  status: BillingStatus;
  stripe_subscription_id?: string;
  current_period_start?: string;
  current_period_end?: string;
  subscription_end?: string;
};

function isBillingPlan(value: string | null | undefined): value is BillingPlan {
  return typeof value === "string" && (BILLING_PLANS as readonly string[]).includes(value);
}

function isBillingStatus(value: string | null | undefined): value is BillingStatus {
  return typeof value === "string" && (BILLING_STATUSES as readonly string[]).includes(value);
}

function toIsoString(unixSeconds: number | null | undefined): string | undefined {
  return typeof unixSeconds === "number" && Number.isFinite(unixSeconds)
    ? new Date(unixSeconds * 1000).toISOString()
    : undefined;
}

function normalizeExistingPlan(existingSubscription?: ExistingSubscription | null): BillingPlan {
  return isBillingPlan(existingSubscription?.plan) ? existingSubscription.plan : "free";
}

function normalizeExistingStatus(existingSubscription?: ExistingSubscription | null): BillingStatus {
  return isBillingStatus(existingSubscription?.status) ? existingSubscription.status : "active";
}

export function normalizeExistingSubscription(
  existingSubscription?: ExistingSubscription | null,
): NormalizedSubscription {
  const currentPeriodEnd = existingSubscription?.current_period_end ?? undefined;

  return {
    subscribed: false,
    plan: normalizeExistingPlan(existingSubscription),
    status: normalizeExistingStatus(existingSubscription),
    stripe_subscription_id: existingSubscription?.stripe_subscription_id ?? undefined,
    current_period_start: existingSubscription?.current_period_start ?? undefined,
    current_period_end: currentPeriodEnd,
    subscription_end: currentPeriodEnd,
  };
}

export function normalizeStripeSubscription(
  stripeSubscription: StripeSubscriptionLike,
  existingSubscription: ExistingSubscription | null | undefined,
  plan: BillingPlan,
): NormalizedSubscription {
  const currentPeriodStart = toIsoString(stripeSubscription.current_period_start)
    ?? existingSubscription?.current_period_start
    ?? undefined;
  const currentPeriodEnd = toIsoString(stripeSubscription.current_period_end)
    ?? existingSubscription?.current_period_end
    ?? undefined;

  return {
    subscribed: true,
    plan,
    status: stripeSubscription.status === "past_due"
      ? "past_due"
      : stripeSubscription.status === "canceled"
        ? "cancelled"
        : "active",
    stripe_subscription_id: stripeSubscription.id ?? existingSubscription?.stripe_subscription_id ?? undefined,
    current_period_start: currentPeriodStart,
    current_period_end: currentPeriodEnd,
    subscription_end: currentPeriodEnd,
  };
}

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
