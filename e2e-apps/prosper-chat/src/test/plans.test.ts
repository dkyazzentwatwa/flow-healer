import { describe, expect, it } from "vitest";

import { PLANS, getPlanBillingSummary } from "@/lib/plans";

describe("getPlanBillingSummary", () => {
  it("returns a zero monthly equivalent for the free plan annual view", () => {
    expect(getPlanBillingSummary(PLANS.free, "annual")).toEqual({
      billedUpfront: null,
      monthlyEquivalent: 0,
    });
  });

  it("returns a rounded monthly equivalent and annual charge for paid annual plans", () => {
    expect(getPlanBillingSummary(PLANS.pro, "annual")).toEqual({
      billedUpfront: 490,
      monthlyEquivalent: 41,
    });
  });
});
