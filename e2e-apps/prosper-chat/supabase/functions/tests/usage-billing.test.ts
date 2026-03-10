import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";

import {
  normalizeExistingSubscription,
  normalizeStripeSubscription,
} from "../_shared/usage-billing.ts";

Deno.test("normalizeExistingSubscription preserves known values and defaults invalid ones safely", () => {
  assertEquals(normalizeExistingSubscription({
    plan: "agency",
    status: "past_due",
    stripe_subscription_id: "sub_existing",
    current_period_start: "2026-03-01T00:00:00.000Z",
    current_period_end: "2026-04-01T00:00:00.000Z",
  }), {
    subscribed: false,
    plan: "agency",
    status: "past_due",
    stripe_subscription_id: "sub_existing",
    current_period_start: "2026-03-01T00:00:00.000Z",
    current_period_end: "2026-04-01T00:00:00.000Z",
    subscription_end: "2026-04-01T00:00:00.000Z",
  });

  assertEquals(normalizeExistingSubscription({
    plan: "enterprise",
    status: "trialing",
  }), {
    subscribed: false,
    plan: "free",
    status: "active",
    stripe_subscription_id: undefined,
    current_period_start: undefined,
    current_period_end: undefined,
    subscription_end: undefined,
  });
});

Deno.test("normalizeStripeSubscription maps statuses and falls back to existing billing periods", () => {
  assertEquals(normalizeStripeSubscription(
    {
      id: "sub_stripe",
      status: "past_due",
      current_period_start: 1_710_000_000,
      current_period_end: 1_712_592_000,
    },
    {
      current_period_start: "2026-03-01T00:00:00.000Z",
      current_period_end: "2026-04-01T00:00:00.000Z",
    },
    "pro",
  ), {
    subscribed: true,
    plan: "pro",
    status: "past_due",
    stripe_subscription_id: "sub_stripe",
    current_period_start: "2024-03-09T16:00:00.000Z",
    current_period_end: "2024-04-08T16:00:00.000Z",
    subscription_end: "2024-04-08T16:00:00.000Z",
  });

  assertEquals(normalizeStripeSubscription(
    {
      status: "canceled",
    },
    {
      stripe_subscription_id: "sub_existing",
      current_period_start: "2026-03-01T00:00:00.000Z",
      current_period_end: "2026-04-01T00:00:00.000Z",
    },
    "agency",
  ), {
    subscribed: true,
    plan: "agency",
    status: "cancelled",
    stripe_subscription_id: "sub_existing",
    current_period_start: "2026-03-01T00:00:00.000Z",
    current_period_end: "2026-04-01T00:00:00.000Z",
    subscription_end: "2026-04-01T00:00:00.000Z",
  });
});
