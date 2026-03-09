export type PlanInterval = "month" | "year" | null | undefined;

export type PlanDefinition = {
  id: string;
  name: string;
  priceInCents: number;
  interval?: PlanInterval;
};

export type PlanBillingSummary = {
  priceInCents: number;
  monthlyEquivalentInCents: number;
  billingInterval: "month" | "year";
  billedAnnually: boolean;
};

const MONTHS_PER_YEAR = 12;

export function getPlanBillingSummary(plan: PlanDefinition): PlanBillingSummary {
  const billingInterval = plan.interval === "year" ? "year" : "month";
  const billedAnnually = billingInterval === "year";
  const monthlyEquivalentInCents = billedAnnually
    ? Math.round(plan.priceInCents / MONTHS_PER_YEAR)
    : plan.priceInCents;

  return {
    priceInCents: plan.priceInCents,
    monthlyEquivalentInCents,
    billingInterval,
    billedAnnually,
  };
}
