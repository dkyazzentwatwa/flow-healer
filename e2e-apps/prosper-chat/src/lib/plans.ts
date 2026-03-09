export type PlanKey = "free" | "pro" | "agency";

export const STRIPE_PRICE_IDS = {
  pro_monthly: "price_1T6H0SEug8OWO1igltVEdgTr",
  pro_annual: "price_1T6H0VEug8OWO1igCCBbG6LI",
  agency_monthly: "price_1T6H0TEug8OWO1iga3B4CyqS",
  agency_annual: "price_1T6H0WEug8OWO1igYBMo9GUr",
} as const;

export interface PlanConfig {
  name: string;
  monthlyPrice: number;
  annualPrice: number;
  description: string;
  limits: {
    chats: number | null;
    leads: number | null;
    businesses: number;
    bots: number | null; // null = unlimited
  };
  features: string[];
  popular?: boolean;
  cta: string;
}

export const PLANS: Record<PlanKey, PlanConfig> = {
  free: {
    name: "Starter",
    monthlyPrice: 0,
    annualPrice: 0,
    description: "For trying it out",
    limits: { chats: 50, leads: 10, businesses: 1, bots: 1 },
    features: [
      "1 business",
      "1 bot",
      "50 chats / month",
      "10 leads / month",
      "Basic FAQs",
      "Email notifications",
    ],
    cta: "Get Started",
  },
  pro: {
    name: "Pro",
    monthlyPrice: 49,
    annualPrice: 490,
    description: "For growing businesses",
    limits: { chats: null, leads: null, businesses: 1, bots: 5 },
    features: [
      "1 business",
      "Up to 5 bots",
      "Unlimited chats",
      "Unlimited leads",
      "Calendly integration",
      "Lead qualification",
      "Analytics dashboard",
      "Priority email support",
    ],
    popular: true,
    cta: "Start Pro Trial",
  },
  agency: {
    name: "Agency",
    monthlyPrice: 149,
    annualPrice: 1490,
    description: "For multi-location businesses",
    limits: { chats: null, leads: null, businesses: 10, bots: null },
    features: [
      "Up to 10 businesses",
      "Unlimited bots",
      "Unlimited chats",
      "Unlimited leads",
      "Custom branding",
      "API access",
      "Priority support",
      "Dedicated account manager",
    ],
    cta: "Contact Sales",
  },
};

export const PLAN_KEYS: PlanKey[] = ["free", "pro", "agency"];

export const COMPARISON_FEATURES = [
  { label: "Businesses", free: "1", pro: "1", agency: "Up to 10" },
  { label: "Bots / widgets", free: "1", pro: "Up to 5", agency: "Unlimited" },
  { label: "Chats / month", free: "50", pro: "Unlimited", agency: "Unlimited" },
  { label: "Leads / month", free: "10", pro: "Unlimited", agency: "Unlimited" },
  { label: "FAQ management", free: true, pro: true, agency: true },
  { label: "Custom bot personality", free: false, pro: true, agency: true },
  { label: "Per-bot FAQ scoping", free: false, pro: true, agency: true },
  { label: "Email notifications", free: true, pro: true, agency: true },
  { label: "Calendly integration", free: false, pro: true, agency: true },
  { label: "Lead qualification", free: false, pro: true, agency: true },
  { label: "Analytics dashboard", free: false, pro: true, agency: true },
  { label: "Custom branding", free: false, pro: false, agency: true },
  { label: "API access", free: false, pro: false, agency: true },
  { label: "Priority support", free: false, pro: false, agency: true },
  { label: "Dedicated account manager", free: false, pro: false, agency: true },
];
