import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const PLAN_RANK: Record<string, number> = { free: 0, pro: 1, agency: 2 };

interface PaywallGateProps {
  children: ReactNode;
  requiredPlan?: "pro" | "agency";
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

  const currentPlan = subscription?.plan ?? "free";
  const hasAccess = (PLAN_RANK[currentPlan] ?? 0) >= (PLAN_RANK[requiredPlan] ?? 1);

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
              {currentPlan} plan
            </Badge>
            <h3 className="text-lg font-semibold">
              Upgrade to {requiredPlan === "agency" ? "Agency" : "Pro"} to unlock Analytics
            </h3>
            <p className="text-sm text-muted-foreground">
              Get detailed insights into conversations, leads, and customer intents.
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
