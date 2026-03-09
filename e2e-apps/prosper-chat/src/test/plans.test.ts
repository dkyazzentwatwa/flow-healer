import assert from "node:assert/strict";
import test from "node:test";

import { getPlanBillingSummary } from "../lib/plans.ts";

test("getPlanBillingSummary keeps the free tier on a stable monthly equivalent", () => {
  assert.deepEqual(
    getPlanBillingSummary({
      id: "free",
      name: "Free",
      priceInCents: 0,
    }),
    {
      priceInCents: 0,
      monthlyEquivalentInCents: 0,
      billingInterval: "month",
      billedAnnually: false,
    },
  );
});

test("getPlanBillingSummary derives a monthly equivalent for annual plans", () => {
  assert.deepEqual(
    getPlanBillingSummary({
      id: "pro-annual",
      name: "Pro Annual",
      priceInCents: 12000,
      interval: "year",
    }),
    {
      priceInCents: 12000,
      monthlyEquivalentInCents: 1000,
      billingInterval: "year",
      billedAnnually: true,
    },
  );
});
