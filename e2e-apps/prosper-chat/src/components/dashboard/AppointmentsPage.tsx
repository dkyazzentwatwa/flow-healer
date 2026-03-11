import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { useToast } from "@/hooks/use-toast";
import { Calendar, Clock } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import type { Database, Tables } from "@/integrations/supabase/types";

type AppointmentStatus = Database["public"]["Enums"]["appointment_status"];
type AppointmentLead = Pick<Tables<"leads">, "first_name" | "email">;
type AppointmentService = Pick<Tables<"services">, "name" | "duration_minutes">;
type AppointmentRow = Tables<"appointments"> & {
  leads: AppointmentLead | null;
  services: AppointmentService | null;
};

const STATUSES: AppointmentStatus[] = ["pending", "confirmed", "cancelled", "completed", "no_show"];

const AppointmentsPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [selected, setSelected] = useState<AppointmentRow | null>(null);
  const [editStatus, setEditStatus] = useState<AppointmentStatus>("pending");
  const [editNotes, setEditNotes] = useState("");

  const openDetail = (a: AppointmentRow) => {
    setSelected(a);
    setEditStatus(a.status);
    setEditNotes(a.notes || "");
  };

  const { data: appointments, isLoading } = useQuery({
    queryKey: ["appointments", business?.id],
    queryFn: async () => {
      const { data } = await supabase
        .from("appointments")
        .select("*, leads(first_name, email), services(name, duration_minutes)")
        .eq("business_id", business!.id)
        .order("start_time", { ascending: true });
      return (data || []) as AppointmentRow[];
    },
    enabled: !!business,
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selected) return;
      const { error } = await supabase.from("appointments").update({
        status: editStatus,
        notes: editNotes || null,
      }).eq("id", selected.id);
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["appointments"] });
      setSelected(null);
      toast({ title: "Appointment updated" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Appointments</h1>
        <p className="text-sm text-muted-foreground">Upcoming bookings made through the chat widget</p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <Skeleton key={i} className="h-18 rounded-lg" />)}
        </div>
      ) : !appointments?.length ? (
        <div className="rounded-lg border p-12 text-center">
          <p className="text-muted-foreground">No appointments yet. They'll appear here when visitors book through your widget.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {appointments.map((a) => (
            <div
              key={a.id}
              onClick={() => openDetail(a)}
              className="flex items-center gap-4 rounded-lg border p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
            >
              <div className="flex h-10 w-10 flex-col items-center justify-center rounded-md bg-secondary">
                <Calendar className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-medium truncate text-sm">
                    {a.leads?.first_name || "Anonymous"}
                  </p>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    a.status === "confirmed" ? "bg-foreground/5 text-foreground" :
                    a.status === "pending" ? "bg-blue/10 text-blue" :
                    "bg-secondary text-muted-foreground"
                  }`}>
                    {a.status}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">{a.services?.name || "—"}</p>
              </div>
              <div className="text-right text-sm">
                <p className="font-medium">{new Date(a.start_time).toLocaleDateString()}</p>
                <p className="flex items-center gap-1 text-muted-foreground justify-end">
                  <Clock className="h-3 w-3" />
                  {new Date(a.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  {" • "}
                  {a.services?.duration_minutes || "?"} min
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Appointment Detail Dialog */}
      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Appointment Details</DialogTitle>
            <DialogDescription>View and manage this appointment</DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Client</p>
                  <p className="font-medium">{selected.leads?.first_name || "Anonymous"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Email</p>
                  <p className="font-medium">{selected.leads?.email || "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Service</p>
                  <p className="font-medium">{selected.services?.name || "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Duration</p>
                  <p className="font-medium">{selected.services?.duration_minutes || "?"} min</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Date</p>
                  <p className="font-medium">{new Date(selected.start_time).toLocaleDateString()}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Time</p>
                  <p className="font-medium">
                    {new Date(selected.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    {" – "}
                    {new Date(selected.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Status</Label>
                <Select value={editStatus} onValueChange={(v) => setEditStatus(v as AppointmentStatus)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((s) => (
                      <SelectItem key={s} value={s} className="capitalize">{s.replace("_", " ")}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Notes</Label>
                <Textarea value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder="Add notes..." />
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

export default AppointmentsPage;
