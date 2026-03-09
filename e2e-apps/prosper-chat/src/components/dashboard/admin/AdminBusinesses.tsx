import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { format } from "date-fns";

const AdminBusinesses = () => {
  const { data: businesses, isLoading } = useQuery({
    queryKey: ["admin-all-businesses"],
    queryFn: async () => {
      const { data } = await supabase
        .from("businesses")
        .select("id, name, owner_id, widget_key, created_at, onboarding_completed")
        .order("created_at", { ascending: false });

      if (!data) return [];

      // Fetch counts per business
      const ids = data.map((b) => b.id);
      const [leadsRes, servicesRes] = await Promise.all([
        supabase.from("leads").select("business_id", { count: "exact" }).in("business_id", ids),
        supabase.from("services").select("business_id", { count: "exact" }).in("business_id", ids),
      ]);

      // Count per business manually since we get all rows
      const leadCounts: Record<string, number> = {};
      const serviceCounts: Record<string, number> = {};
      leadsRes.data?.forEach((l) => { leadCounts[l.business_id] = (leadCounts[l.business_id] || 0) + 1; });
      servicesRes.data?.forEach((s) => { serviceCounts[s.business_id] = (serviceCounts[s.business_id] || 0) + 1; });

      return data.map((b) => ({
        ...b,
        leadCount: leadCounts[b.id] || 0,
        serviceCount: serviceCounts[b.id] || 0,
      }));
    },
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">All Businesses</h1>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Widget Key</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Leads</TableHead>
                <TableHead className="text-right">Services</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
              ) : businesses?.length ? (
                businesses.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell className="font-medium">{b.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{b.widget_key}</TableCell>
                    <TableCell>
                      <Badge variant={b.onboarding_completed ? "default" : "secondary"}>
                        {b.onboarding_completed ? "Active" : "Onboarding"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">{b.leadCount}</TableCell>
                    <TableCell className="text-right">{b.serviceCount}</TableCell>
                    <TableCell className="text-muted-foreground">{format(new Date(b.created_at), "MMM d, yyyy")}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">No businesses</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminBusinesses;
