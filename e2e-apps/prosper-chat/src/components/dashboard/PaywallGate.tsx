import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PLANS, type PlanKey } from "@/lib/plans";

const PLAN_RANK: Record<PlanKey, number> = { free: 0, pro: 1, agency: 2 };

function formatLimit(value: number | null, label: string) {
  if (value === null) return `Unlimited ${label}`;
  return `${value} ${label}`;
}

function getUsageSummary(planKey: PlanKey) {
  const plan = PLANS[planKey];

  return [
    formatLimit(plan.limits.chats, "chats / month"),
    formatLimit(plan.limits.leads, "leads / month"),
    formatLimit(plan.limits.bots, "bot" + (plan.limits.bots === 1 ? "" : "s")),
  ].join(", ");
}

interface PaywallGateProps {
  children: ReactNode;
  requiredPlan?: Exclude<PlanKey, "free">;
}

const PaywallGate = ({ children, requiredPlan = "pro" }: PaywallGateProps) => {
  const { activeBusiness: business } = useActiveBusiness();

  const { data: subscription } = useQuery({
    queryKey: ["subscription", business?.id],
    enabled: !!business?.id,
    queryFn: async () => {
      const { data } = await supabase
        .from("subscriptions")
        .select("plan, status")
        .eq("business_id", business!.id)
        .eq("status", "active")
        .limit(1)
        .maybeSingle();
      return data;
    },
  });

  const currentPlan = (subscription?.plan ?? "free") as PlanKey;
  const currentPlanConfig = PLANS[currentPlan];
  const requiredPlanConfig = PLANS[requiredPlan];
  const hasAccess = PLAN_RANK[currentPlan] >= PLAN_RANK[requiredPlan];

  if (hasAccess) return <>{children}</>;

  return (
    <div className="relative">
      <div className="blur-sm pointer-events-none select-none" aria-hidden>
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center bg-background/40 z-10">
        <Card className="max-w-sm text-center shadow-lg">
          <CardContent className="pt-8 pb-6 px-8 flex flex-col items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              <Lock className="h-6 w-6 text-muted-foreground" />
            </div>
            <Badge variant="secondary" className="uppercase text-xs tracking-wider">
              {currentPlanConfig.name} plan
            </Badge>
            <h3 className="text-lg font-semibold">
              Upgrade to {requiredPlanConfig.name} to unlock Analytics
            </h3>
            <p className="text-sm text-muted-foreground">
              Your {currentPlanConfig.name} plan includes {getUsageSummary(currentPlan)}.
              Upgrade to {requiredPlanConfig.name} for {getUsageSummary(requiredPlan)} and analytics insights.
            </p>
            <Button asChild className="w-full mt-2">
              <Link to="/dashboard/billing">Upgrade Now</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default PaywallGate;
