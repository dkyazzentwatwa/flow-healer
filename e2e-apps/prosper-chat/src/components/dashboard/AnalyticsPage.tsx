import { useActiveBusiness } from "@/contexts/BusinessContext";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import PaywallGate from "./PaywallGate";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { MessageCircle, Users, AlertTriangle, UserCheck } from "lucide-react";
import { subDays, format, startOfDay } from "date-fns";
import { Json } from "@/integrations/supabase/types";

const COLORS = [
  "hsl(var(--primary))",
  "hsl(var(--secondary))",
  "hsl(var(--accent))",
  "hsl(var(--muted-foreground))",
];

const AnalyticsPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const businessId = business?.id;

  const { data: conversations = [] } = useQuery({
    queryKey: ["analytics-conversations", businessId],
    enabled: !!businessId,
    queryFn: async () => {
      const { data } = await supabase
        .from("conversations")
        .select("id, created_at, messages, escalated, intent, lead_id")
        .eq("business_id", businessId!);
      return data ?? [];
    },
  });

  const { data: leads = [] } = useQuery({
    queryKey: ["analytics-leads", businessId],
    enabled: !!businessId,
    queryFn: async () => {
      const { data } = await supabase
        .from("leads")
        .select("id, status")
        .eq("business_id", businessId!);
      return data ?? [];
    },
  });

  // --- Conversations over time (last 30 days) ---
  const thirtyDaysAgo = subDays(new Date(), 30);
  const convByDay = conversations.reduce<Record<string, number>>((acc, c) => {
    const d = format(startOfDay(new Date(c.created_at)), "MMM dd");
    acc[d] = (acc[d] || 0) + 1;
    return acc;
  }, {});
  const convTimeline = Array.from({ length: 30 }, (_, i) => {
    const d = format(subDays(new Date(), 29 - i), "MMM dd");
    return { date: d, count: convByDay[d] || 0 };
  });

  // --- Lead funnel ---
  const funnelOrder = ["new", "contacted", "qualified", "converted"] as const;
  const leadFunnel = funnelOrder.map((s) => ({
    stage: s.charAt(0).toUpperCase() + s.slice(1),
    count: leads.filter((l) => l.status === s).length,
  }));

  // --- Top intents ---
  const intentCounts: Record<string, number> = {};
  conversations.forEach((c) => {
    if (c.intent) intentCounts[c.intent] = (intentCounts[c.intent] || 0) + 1;
  });
  const topIntents = Object.entries(intentCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([intent, count]) => ({ intent, count }));

  // --- Metrics ---
  const totalConvos = conversations.length;
  const avgMessages =
    totalConvos > 0
      ? (
          conversations.reduce((sum, c) => {
            const msgs = c.messages as Json;
            return sum + (Array.isArray(msgs) ? msgs.length : 0);
          }, 0) / totalConvos
        ).toFixed(1)
      : "0";
  const escalationRate =
    totalConvos > 0
      ? ((conversations.filter((c) => c.escalated).length / totalConvos) * 100).toFixed(1)
      : "0";
  const leadCaptureRate =
    totalConvos > 0
      ? ((conversations.filter((c) => c.lead_id).length / totalConvos) * 100).toFixed(1)
      : "0";

  const metrics = [
    { label: "Total Conversations", value: totalConvos, icon: MessageCircle },
    { label: "Avg Messages / Convo", value: avgMessages, icon: Users },
    { label: "Escalation Rate", value: `${escalationRate}%`, icon: AlertTriangle },
    { label: "Lead Capture Rate", value: `${leadCaptureRate}%`, icon: UserCheck },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-sm text-muted-foreground">Insights into your chatbot performance.</p>
      </div>

      <PaywallGate requiredPlan="pro">
        <div className="space-y-6">
          {/* Key metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {metrics.map((m) => (
              <Card key={m.label}>
                <CardContent className="pt-5 pb-4 flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
                    <m.icon className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold leading-none">{m.value}</p>
                    <p className="text-xs text-muted-foreground mt-1">{m.label}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Conversations over time */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Conversations (Last 30 Days)</CardTitle>
            </CardHeader>
            <CardContent className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={convTimeline}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="count" stroke="hsl(var(--primary))" fill="hsl(var(--primary) / 0.2)" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <div className="grid md:grid-cols-2 gap-6">
            {/* Lead Funnel */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Lead Funnel</CardTitle>
              </CardHeader>
              <CardContent className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={leadFunnel}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="stage" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {leadFunnel.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Top Intents */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Top Intents</CardTitle>
              </CardHeader>
              <CardContent className="h-64">
                {topIntents.length === 0 ? (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    No intent data yet
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={topIntents} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="intent" width={100} tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </PaywallGate>
    </div>
  );
};

export default AnalyticsPage;
