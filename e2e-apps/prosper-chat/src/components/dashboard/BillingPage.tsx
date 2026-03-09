import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { PLANS, PLAN_KEYS, STRIPE_PRICE_IDS, type PlanKey } from "@/lib/plans";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/hooks/use-toast";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, CreditCard, TrendingUp, Zap, ExternalLink } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { format, eachDayOfInterval, endOfMonth, startOfMonth } from "date-fns";
import { useSearchParams } from "react-router-dom";

function getBoundedUsagePercent(count: number, limit: number | null): number {
  if (!limit || !Number.isFinite(limit) || limit <= 0) {
    return 0;
  }

  const safeCount = Number.isFinite(count) ? count : 0;
  const percent = Math.round((safeCount / limit) * 100);

  return Math.min(Math.max(percent, 0), 100);
}

const BillingPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const [billingCycle, setBillingCycle] = useState<"monthly" | "annual">("monthly");
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [searchParams] = useSearchParams();

  // Show toast on checkout return
  useEffect(() => {
    const checkout = searchParams.get("checkout");
    if (checkout === "success") {
      toast({ title: "Subscription activated!", description: "Your plan has been upgraded. It may take a moment to reflect." });
    } else if (checkout === "cancelled") {
      toast({ title: "Checkout cancelled", description: "No changes were made to your plan." });
    }
  }, [searchParams]);

  // Check subscription from Stripe
  const { data: stripeStatus, refetch: refetchStripe } = useQuery({
    queryKey: ["stripe-subscription"],
    queryFn: async () => {
      const { data, error } = await supabase.functions.invoke("check-subscription");
      if (error) throw error;
      return data as { subscribed: boolean; plan: PlanKey; subscription_end?: string; stripe_subscription_id?: string };
    },
    refetchInterval: 60_000,
  });

  // Fetch local subscription
  const { data: subscription, isLoading: subLoading } = useQuery({
    queryKey: ["subscription", business?.id],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("subscriptions")
        .select("*")
        .eq("business_id", business!.id)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
    enabled: !!business,
  });

  // Prefer Stripe plan only if actively subscribed; otherwise use local DB plan
  const currentPlan: PlanKey = stripeStatus?.subscribed
    ? (stripeStatus.plan as PlanKey)
    : (subscription?.plan as PlanKey) || "free";
  const planConfig = PLANS[currentPlan];
  const periodStart = subscription?.current_period_start
    ? new Date(subscription.current_period_start)
    : startOfMonth(new Date());
  const periodEnd = subscription?.current_period_end
    ? new Date(subscription.current_period_end)
    : endOfMonth(new Date());

  // Fetch usage records
  const { data: usageRecords, isLoading: usageLoading } = useQuery({
    queryKey: ["usage", business?.id, periodStart.toISOString()],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("usage_records")
        .select("*")
        .eq("business_id", business!.id)
        .gte("recorded_at", periodStart.toISOString())
        .lte("recorded_at", periodEnd.toISOString());
      if (error) throw error;
      return data || [];
    },
    enabled: !!business,
  });

  const chatCount = usageRecords?.filter((r: any) => r.type === "chat").length || 0;
  const leadCount = usageRecords?.filter((r: any) => r.type === "lead_captured").length || 0;
  const appointmentCount = usageRecords?.filter((r: any) => r.type === "appointment_booked").length || 0;

  const chartData = (() => {
    if (!usageRecords) return [];
    const days = eachDayOfInterval({ start: periodStart, end: new Date() > periodEnd ? periodEnd : new Date() });
    return days.map((day) => {
      const dayStr = format(day, "yyyy-MM-dd");
      const chats = usageRecords.filter(
        (r: any) => r.type === "chat" && format(new Date(r.recorded_at), "yyyy-MM-dd") === dayStr
      ).length;
      return { date: format(day, "MMM d"), chats };
    });
  })();

  const chatLimit = planConfig.limits.chats;
  const leadLimit = planConfig.limits.leads;
  const chatPct = getBoundedUsagePercent(chatCount, chatLimit);

  const handleCheckout = async (planKey: PlanKey) => {
    if (planKey === "free") return;
    setCheckoutLoading(planKey);
    try {
      const priceId = planKey === "pro"
        ? (billingCycle === "annual" ? STRIPE_PRICE_IDS.pro_annual : STRIPE_PRICE_IDS.pro_monthly)
        : (billingCycle === "annual" ? STRIPE_PRICE_IDS.agency_annual : STRIPE_PRICE_IDS.agency_monthly);

      const { data, error } = await supabase.functions.invoke("create-checkout", {
        body: { priceId },
      });
      if (error) throw error;
      if (data?.url) {
        const opened = window.open(data.url, "_blank", "noopener,noreferrer");
        if (!opened) {
          window.location.href = data.url;
        }
      }
    } catch (err: any) {
      toast({ title: "Checkout error", description: err.message || "Could not start checkout", variant: "destructive" });
    } finally {
      setCheckoutLoading(null);
    }
  };

  const handleManageSubscription = async () => {
    setPortalLoading(true);
    try {
      const { data, error } = await supabase.functions.invoke("customer-portal");
      if (error) throw error;
      if (data?.url) {
        const opened = window.open(data.url, "_blank", "noopener,noreferrer");
        if (!opened) {
          window.location.href = data.url;
        }
      }
    } catch (err: any) {
      toast({ title: "Portal error", description: err.message || "Could not open portal", variant: "destructive" });
    } finally {
      setPortalLoading(false);
    }
  };

  if (!business) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-3"><Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-40" /></div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Usage & Billing</h1>
        <p className="text-sm text-muted-foreground">Monitor usage and manage your plan.</p>
      </div>

      {/* Current Plan Card */}
      <div className="rounded-lg border p-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-lg font-semibold">{planConfig.name} Plan</h2>
              <Badge variant="secondary" className="text-xs">
                {subscription?.status || "active"}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {format(periodStart, "MMM d, yyyy")} — {format(periodEnd, "MMM d, yyyy")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {stripeStatus?.subscribed && (
              <Button variant="outline" size="sm" onClick={handleManageSubscription} disabled={portalLoading}>
                <ExternalLink className="h-4 w-4 mr-1" />
                {portalLoading ? "Opening..." : "Manage Subscription"}
              </Button>
            )}
            <div className="text-right">
              <p className="text-3xl font-bold tracking-tight">
                {planConfig.monthlyPrice === 0 ? "Free" : `$${billingCycle === "annual" ? Math.round(planConfig.annualPrice / 12) : planConfig.monthlyPrice}`}
              </p>
              {planConfig.monthlyPrice > 0 && <p className="text-xs text-muted-foreground">per month</p>}
            </div>
          </div>
        </div>
      </div>

      {/* Usage Stats Row */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-muted-foreground">Chats</p>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-2xl font-semibold">
            {chatCount}{chatLimit ? ` / ${chatLimit}` : ""}
          </p>
          {chatLimit && (
            <div className="mt-2 h-1.5 rounded-full bg-secondary">
              <div
                data-testid="chat-usage-meter"
                className={`h-1.5 rounded-full transition-all ${chatPct >= 100 ? "bg-destructive" : chatPct >= 80 ? "bg-chart-4" : "bg-foreground"}`}
                style={{ width: `${chatPct}%` }}
              />
            </div>
          )}
        </div>
        <div className="rounded-lg border p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-muted-foreground">Leads Captured</p>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-2xl font-semibold">
            {leadCount}{leadLimit ? ` / ${leadLimit}` : ""}
          </p>
        </div>
        <div className="rounded-lg border p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-muted-foreground">Appointments</p>
            <CreditCard className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-2xl font-semibold">{appointmentCount}</p>
        </div>
      </div>

      {/* Usage Chart */}
      <div className="rounded-lg border p-6">
        <h2 className="mb-4 text-sm font-medium">Daily Chat Volume</h2>
        {usageLoading ? (
          <Skeleton className="h-52 w-full" />
        ) : chartData.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">No usage data yet for this period.</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} className="fill-muted-foreground" />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} className="fill-muted-foreground" />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }}
              />
              <Bar dataKey="chats" fill="hsl(var(--foreground))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Plan Comparison */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Plans</h2>
          <div className="inline-flex items-center gap-1 rounded-full border p-1">
            <button
              onClick={() => setBillingCycle("monthly")}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                billingCycle === "monthly" ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setBillingCycle("annual")}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                billingCycle === "annual" ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Annual
            </button>
          </div>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {PLAN_KEYS.map((key) => {
            const plan = PLANS[key];
            const isCurrent = key === currentPlan;
            const price = billingCycle === "annual" ? Math.round(plan.annualPrice / 12) : plan.monthlyPrice;
            return (
              <div
                key={key}
                className={`relative rounded-lg border p-6 transition-shadow ${
                  plan.popular ? "border-foreground ring-1 ring-foreground shadow-lg scale-[1.02]" : ""
                } ${isCurrent ? "bg-secondary/30" : ""}`}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-foreground px-3 py-0.5 text-xs font-medium text-background">
                    Most Popular
                  </div>
                )}
                {isCurrent && (
                  <Badge className="absolute top-3 right-3 text-[10px]" variant="outline">Current</Badge>
                )}
                <h3 className="font-semibold">{plan.name}</h3>
                <p className="text-sm text-muted-foreground">{plan.description}</p>
                <p className="my-4 text-4xl font-bold tracking-tight">
                  {price === 0 ? "Free" : `$${price}`}
                  {price > 0 && <span className="text-sm font-normal text-muted-foreground">/mo</span>}
                </p>
                {billingCycle === "annual" && plan.annualPrice > 0 && (
                  <p className="text-xs text-muted-foreground -mt-2 mb-4">${plan.annualPrice} billed annually</p>
                )}
                <ul className="mb-6 space-y-2 text-sm">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-muted-foreground">
                      <CheckCircle2 className="h-4 w-4 text-foreground shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Button
                  variant={plan.popular ? "default" : "outline"}
                  className="w-full"
                  disabled={isCurrent || checkoutLoading === key}
                  onClick={() => {
                    if (key === "free") return;
                    handleCheckout(key);
                  }}
                >
                  {isCurrent ? "Current Plan" : checkoutLoading === key ? "Redirecting..." : plan.cta}
                </Button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default BillingPage;
