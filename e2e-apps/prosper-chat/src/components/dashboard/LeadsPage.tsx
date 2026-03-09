import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import type { Database } from "@/integrations/supabase/types";

type LeadStatus = Database["public"]["Enums"]["lead_status"];

const statusColor: Record<string, string> = {
  new: "bg-foreground/5 text-foreground",
  qualified: "bg-blue/10 text-blue",
  contacted: "bg-secondary text-muted-foreground",
  converted: "bg-foreground/10 text-foreground",
  lost: "bg-destructive/10 text-destructive",
};

const STATUSES: LeadStatus[] = ["new", "contacted", "qualified", "converted", "lost"];

const LeadsPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [selected, setSelected] = useState<any>(null);
  const [editStatus, setEditStatus] = useState<LeadStatus>("new");
  const [editNotes, setEditNotes] = useState("");

  const openDetail = (lead: any) => {
    setSelected(lead);
    setEditStatus(lead.status);
    setEditNotes(lead.notes || "");
  };

  const { data: leads, isLoading } = useQuery({
    queryKey: ["leads", business?.id],
    queryFn: async () => {
      const { data } = await supabase
        .from("leads")
        .select("*")
        .eq("business_id", business!.id)
        .order("created_at", { ascending: false });
      return data || [];
    },
    enabled: !!business,
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      const { error } = await supabase.from("leads").update({
        status: editStatus,
        notes: editNotes || null,
      }).eq("id", selected.id);
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["leads"] });
      setSelected(null);
      toast({ title: "Lead updated" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Leads</h1>
        <p className="text-sm text-muted-foreground">All captured leads from your chat widget</p>
      </div>

      {isLoading ? (
        <div className="rounded-lg border p-5 space-y-3">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      ) : !leads?.length ? (
        <div className="rounded-lg border p-12 text-center">
          <p className="text-muted-foreground">No leads yet. They'll appear here when visitors interact with your widget.</p>
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-secondary/50">
                  <th className="px-5 py-3 text-left font-medium text-muted-foreground">Name</th>
                  <th className="px-5 py-3 text-left font-medium text-muted-foreground">Status</th>
                  <th className="px-5 py-3 text-left font-medium text-muted-foreground">Contact</th>
                  <th className="px-5 py-3 text-left font-medium text-muted-foreground">Source</th>
                  <th className="px-5 py-3 text-left font-medium text-muted-foreground">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {leads.map((l) => (
                  <tr
                    key={l.id}
                    onClick={() => openDetail(l)}
                    className="hover:bg-secondary/30 transition-colors cursor-pointer"
                  >
                    <td className="px-5 py-3 font-medium">{l.first_name || "Anonymous"}</td>
                    <td className="px-5 py-3">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor[l.status] || ""}`}>
                        {l.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-muted-foreground">{l.email || l.phone || "—"}</td>
                    <td className="px-5 py-3 text-muted-foreground">{l.source || "widget"}</td>
                    <td className="px-5 py-3 text-muted-foreground">{new Date(l.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Lead Detail Dialog */}
      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{selected?.first_name || "Anonymous"}</DialogTitle>
            <DialogDescription>Lead details and management</DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Email</p>
                  <p className="font-medium">{selected.email || "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Phone</p>
                  <p className="font-medium">{selected.phone || "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Source</p>
                  <p className="font-medium">{selected.source || "widget"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Returning</p>
                  <p className="font-medium">{selected.is_returning ? "Yes" : "No"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Created</p>
                  <p className="font-medium">{new Date(selected.created_at).toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Updated</p>
                  <p className="font-medium">{new Date(selected.updated_at).toLocaleString()}</p>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Status</Label>
                <Select value={editStatus} onValueChange={(v) => setEditStatus(v as LeadStatus)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((s) => (
                      <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Notes</Label>
                <Textarea value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder="Add notes about this lead..." />
              </div>

              <DialogFooter>
                <Button onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>
                  {updateMutation.isPending ? "Saving..." : "Save Changes"}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LeadsPage;
