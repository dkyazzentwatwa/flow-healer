import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { Calendar, Users, MessageCircle, Briefcase, CheckCircle2, Circle, AlertTriangle } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Link } from "react-router-dom";
import { PLANS, type PlanKey } from "@/lib/plans";

const DashboardHome = () => {
  const { activeBusiness: business } = useActiveBusiness();

  const { data: leads, isLoading: leadsLoading } = useQuery({
    queryKey: ["leads", business?.id],
    queryFn: async () => {
      const { data } = await supabase.from("leads").select("*").eq("business_id", business!.id).order("created_at", { ascending: false }).limit(10);
      return data || [];
    },
    enabled: !!business,
  });

  const { data: appointmentCount } = useQuery({
    queryKey: ["appointment-count", business?.id],
    queryFn: async () => {
      const { count } = await supabase.from("appointments").select("*", { count: "exact", head: true }).eq("business_id", business!.id);
      return count || 0;
    },
    enabled: !!business,
  });

  const { data: conversationCount } = useQuery({
    queryKey: ["conversation-count", business?.id],
    queryFn: async () => {
      const { count } = await supabase.from("conversations").select("*", { count: "exact", head: true }).eq("business_id", business!.id);
      return count || 0;
    },
    enabled: !!business,
  });

  const { data: serviceCount } = useQuery({
    queryKey: ["service-count", business?.id],
    queryFn: async () => {
      const { count } = await supabase.from("services").select("*", { count: "exact", head: true }).eq("business_id", business!.id);
      return count || 0;
    },
    enabled: !!business,
  });

  const { data: faqCount } = useQuery({
    queryKey: ["faq-count", business?.id],
    queryFn: async () => {
      const { count } = await supabase.from("faqs").select("*", { count: "exact", head: true }).eq("business_id", business!.id);
      return count || 0;
    },
    enabled: !!business,
  });

  // Fetch subscription & usage for warning banner
  const { data: subscription } = useQuery({
    queryKey: ["subscription", business?.id],
    queryFn: async () => {
      const { data } = await supabase.from("subscriptions").select("*").eq("business_id", business!.id).maybeSingle();
      return data;
    },
    enabled: !!business,
  });

  const { data: chatUsageCount } = useQuery({
    queryKey: ["chat-usage-count", business?.id],
    queryFn: async () => {
      const periodStart = subscription?.current_period_start || new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString();
      const { count } = await supabase
        .from("usage_records")
        .select("*", { count: "exact", head: true })
        .eq("business_id", business!.id)
        .eq("type", "chat")
        .gte("recorded_at", periodStart);
      return count || 0;
    },
    enabled: !!business && !!subscription,
  });

  const currentPlan = (subscription?.plan as PlanKey) || "free";
  const chatLimit = PLANS[currentPlan]?.limits.chats;
  const chatPct = chatLimit ? Math.round(((chatUsageCount || 0) / chatLimit) * 100) : 0;
  const showUsageWarning = chatLimit && chatPct >= 80;

  const stats = [
    { label: "Leads", value: String(leads?.length || 0), icon: Users },
    { label: "Appointments", value: String(appointmentCount || 0), icon: Calendar },
    { label: "Conversations", value: String(conversationCount || 0), icon: MessageCircle },
    { label: "Active Services", value: String(serviceCount || 0), icon: Briefcase },
  ];

  const setupItems = [
    { label: "Business profile configured", done: !!(business?.phone || business?.address) },
    { label: "At least one service added", done: (serviceCount || 0) > 0 },
    { label: "At least one FAQ added", done: (faqCount || 0) > 0 },
    { label: "Widget embedded on your site", done: false },
  ];
  const setupDone = setupItems.filter((i) => i.done).length;

  const statusColor: Record<string, string> = {
    new: "bg-foreground/5 text-foreground",
    qualified: "bg-blue/10 text-blue",
    contacted: "bg-secondary text-muted-foreground",
    converted: "bg-foreground/10 text-foreground",
    lost: "bg-destructive/10 text-destructive",
  };

  if (!business) {
    return (
      <div className="space-y-6">
        <div><Skeleton className="h-8 w-48" /><Skeleton className="h-4 w-32 mt-2" /></div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-24 rounded-lg" />)}
        </div>
        <Skeleton className="h-64 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Welcome back, {business.name}</p>
      </div>

      {showUsageWarning && (
        <div className={`flex items-center gap-3 rounded-lg border p-4 ${chatPct >= 100 ? "border-destructive bg-destructive/5" : "border-chart-4 bg-chart-4/5"}`}>
          <AlertTriangle className={`h-5 w-5 shrink-0 ${chatPct >= 100 ? "text-destructive" : "text-chart-4"}`} />
          <div className="flex-1">
            <p className="text-sm font-medium">
              {chatPct >= 100
                ? "You've reached your monthly chat limit"
                : `You've used ${chatPct}% of your monthly chats`}
            </p>
            <p className="text-xs text-muted-foreground">
              {chatUsageCount} / {chatLimit} chats used this period.{" "}
              <Link to="/dashboard/billing" className="underline hover:text-foreground">Upgrade your plan</Link> for unlimited chats.
            </p>
          </div>
        </div>
      )}

      {setupDone < setupItems.length && (
        <div className="rounded-lg border p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium">Setup Progress</h2>
            <span className="text-xs text-muted-foreground">{setupDone}/{setupItems.length} complete</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-secondary mb-4">
            <div className="h-1.5 rounded-full bg-foreground transition-all" style={{ width: `${(setupDone / setupItems.length) * 100}%` }} />
          </div>
          <div className="space-y-2">
            {setupItems.map((item) => (
              <div key={item.label} className="flex items-center gap-2 text-sm">
                {item.done ? (
                  <CheckCircle2 className="h-4 w-4 text-foreground" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground/40" />
                )}
                <span className={item.done ? "text-muted-foreground line-through" : ""}>{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg border p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">{s.label}</p>
              <s.icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <p className="mt-2 text-2xl font-semibold tracking-tight">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border">
        <div className="border-b px-5 py-4">
          <h2 className="text-sm font-medium">Recent Leads</h2>
        </div>
        {leadsLoading ? (
          <div className="p-5 space-y-3">
            {[1,2,3].map(i => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : !leads?.length ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">No leads yet. They'll appear here when visitors interact with your widget.</p>
        ) : (
          <div className="divide-y">
            {leads.map((lead) => (
              <div key={lead.id} className="flex items-center justify-between px-5 py-3">
                <div>
                  <p className="text-sm font-medium">{lead.first_name || "Anonymous"}</p>
                  <p className="text-xs text-muted-foreground">{lead.email || lead.phone || "No contact"}</p>
                </div>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor[lead.status] || ""}`}>
                  {lead.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DashboardHome;
