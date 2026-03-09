import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

const AdminUsers = () => {
  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-all-users"],
    queryFn: async () => {
      // Get all roles
      const { data: roles } = await supabase.from("user_roles").select("user_id, role");
      if (!roles?.length) return [];

      // Get all businesses to map owner_id → business name & email
      const { data: businesses } = await supabase.from("businesses").select("owner_id, name, email");

      const bizMap: Record<string, { name: string; email: string | null }> = {};
      businesses?.forEach((b) => { bizMap[b.owner_id] = { name: b.name, email: b.email }; });

      return roles.map((r) => ({
        userId: r.user_id,
        role: r.role,
        businessName: bizMap[r.user_id]?.name ?? "—",
        email: bizMap[r.user_id]?.email ?? "—",
      }));
    },
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">All Users</h1>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Business</TableHead>
                <TableHead className="font-mono text-xs">User ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
              ) : users?.length ? (
                users.map((u) => (
                  <TableRow key={`${u.userId}-${u.role}`}>
                    <TableCell>{u.email}</TableCell>
                    <TableCell>
                      <Badge variant={u.role === "admin" ? "default" : "secondary"}>{u.role}</Badge>
                    </TableCell>
                    <TableCell>{u.businessName}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{u.userId.slice(0, 8)}…</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">No users</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminUsers;
