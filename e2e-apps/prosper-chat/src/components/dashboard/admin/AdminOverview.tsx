import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Building2, Users, Calendar, MessageCircle } from "lucide-react";
import { format } from "date-fns";

const AdminOverview = () => {
  const { data: stats } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: async () => {
      const [businesses, leads, appointments, conversations] = await Promise.all([
        supabase.from("businesses").select("id", { count: "exact", head: true }),
        supabase.from("leads").select("id", { count: "exact", head: true }),
        supabase.from("appointments").select("id", { count: "exact", head: true }),
        supabase.from("conversations").select("id", { count: "exact", head: true }),
      ]);
      return {
        businesses: businesses.count ?? 0,
        leads: leads.count ?? 0,
        appointments: appointments.count ?? 0,
        conversations: conversations.count ?? 0,
      };
    },
  });

  const { data: recentBusinesses } = useQuery({
    queryKey: ["admin-recent-businesses"],
    queryFn: async () => {
      const { data } = await supabase
        .from("businesses")
        .select("id, name, owner_id, widget_key, created_at")
        .order("created_at", { ascending: false })
        .limit(10);
      return data ?? [];
    },
  });

  const statCards = [
    { label: "Businesses", value: stats?.businesses ?? 0, icon: Building2 },
    { label: "Leads", value: stats?.leads ?? 0, icon: Users },
    { label: "Appointments", value: stats?.appointments ?? 0, icon: Calendar },
    { label: "Conversations", value: stats?.conversations ?? 0, icon: MessageCircle },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Admin Overview</h1>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((s) => (
          <Card key={s.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{s.label}</CardTitle>
              <s.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold">{s.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Businesses</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Widget Key</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentBusinesses?.map((b) => (
                <TableRow key={b.id}>
                  <TableCell className="font-medium">{b.name}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{b.widget_key}</TableCell>
                  <TableCell className="text-muted-foreground">{format(new Date(b.created_at), "MMM d, yyyy")}</TableCell>
                </TableRow>
              ))}
              {!recentBusinesses?.length && (
                <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground">No businesses yet</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminOverview;
