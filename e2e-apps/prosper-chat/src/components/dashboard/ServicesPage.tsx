import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Plus, Clock, DollarSign, Trash2, ChevronDown, ChevronRight, Bot, Inbox } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { industryTemplates } from "@/data/industryTemplates";
import type { Tables } from "@/integrations/supabase/types";

const ServicesPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState("");
  const [duration, setDuration] = useState("30");
  const [price, setPrice] = useState("");
  const [description, setDescription] = useState("");

  // Edit modal state
  const [editService, setEditService] = useState<Tables<"services"> | null>(null);
  const [editName, setEditName] = useState("");
  const [editDuration, setEditDuration] = useState("");
  const [editPrice, setEditPrice] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editActive, setEditActive] = useState(true);

  // Collapsed sections state
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  const toggleSection = (key: string) => {
    setCollapsedSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const openEdit = (s: Tables<"services">) => {
    setEditService(s);
    setEditName(s.name);
    setEditDuration(String(s.duration_minutes));
    setEditPrice(s.price_text || "");
    setEditDescription(s.description || "");
    setEditActive(s.is_active ?? true);
  };

  const { data: services, isLoading } = useQuery({
    queryKey: ["services", business?.id],
    queryFn: async () => {
      const { data } = await supabase.from("services").select("*").eq("business_id", business!.id).order("sort_order");
      return data || [];
    },
    enabled: !!business,
  });

  const { data: bots } = useQuery({
    queryKey: ["bots", business?.id],
    queryFn: async () => {
      const { data } = await supabase.from("bots").select("*").eq("business_id", business!.id).order("created_at");
      return data || [];
    },
    enabled: !!business,
  });

  // Group services by bot
  const groupedServices = useMemo(() => {
    if (!services || !bots) return [];

    const groups: { key: string; label: string; templateName?: string; botName?: string; items: typeof services }[] = [];
    const assigned = new Set<string>();

    for (const bot of bots) {
      if (!bot.service_ids?.length) continue;
      const scopedIds = new Set(bot.service_ids as string[]);
      const items = services.filter(s => scopedIds.has(s.id));
      if (!items.length) continue;
      items.forEach(s => assigned.add(s.id));

      const tpl = bot.template_id ? industryTemplates.find(t => t.id === bot.template_id) : null;
      groups.push({
        key: bot.id,
        label: bot.name,
        botName: bot.name,
        templateName: tpl?.name,
        items,
      });
    }

    // Bots with no service_ids (uses all) — don't create a group, those services show in unassigned
    const unassigned = services.filter(s => !assigned.has(s.id));
    if (unassigned.length) {
      groups.push({ key: "__unassigned", label: "Shared / Unassigned", items: unassigned });
    }

    // If no bots have scoped services, show everything flat under one group
    if (groups.length === 0) {
      groups.push({ key: "__all", label: "All Services", items: services });
    }

    return groups;
  }, [services, bots]);

  const addMutation = useMutation({
    mutationFn: async () => {
      const { error } = await supabase.from("services").insert({
        business_id: business!.id, name, duration_minutes: parseInt(duration), price_text: price, description,
      });
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["services"] });
      setShowAdd(false);
      setName(""); setDuration("30"); setPrice(""); setDescription("");
      toast({ title: "Service added" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editService) return;
      const { error } = await supabase.from("services").update({
        name: editName,
        duration_minutes: parseInt(editDuration),
        price_text: editPrice || null,
        description: editDescription || null,
        is_active: editActive,
      }).eq("id", editService.id);
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["services"] });
      setEditService(null);
      toast({ title: "Service updated" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) => {
      const { error } = await supabase.from("services").update({ is_active }).eq("id", id);
      if (error) throw error;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["services"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from("services").delete().eq("id", id);
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["services"] });
      setEditService(null);
      toast({ title: "Service deleted" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const renderServiceCard = (s: Tables<"services">) => (
    <div
      key={s.id}
      onClick={() => openEdit(s)}
      className={`rounded-lg border p-5 transition-colors hover:bg-secondary/30 cursor-pointer ${!s.is_active ? "opacity-50" : ""}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium">{s.name}</h3>
          {s.description && <p className="mt-1 text-xs text-muted-foreground">{s.description}</p>}
        </div>
        <div className="flex items-center gap-2 ml-2">
          <button
            onClick={(e) => { e.stopPropagation(); toggleMutation.mutate({ id: s.id, is_active: !s.is_active }); }}
            className={`h-2 w-2 rounded-full ${s.is_active ? "bg-foreground" : "bg-muted-foreground"}`}
            title={s.is_active ? "Active" : "Inactive"}
          />
          <button
            onClick={(e) => { e.stopPropagation(); if (confirm("Delete this service?")) deleteMutation.mutate(s.id); }}
            className="text-muted-foreground/40 hover:text-destructive transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <div className="mt-4 flex items-center gap-4 text-sm text-muted-foreground">
        <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> {s.duration_minutes} min</span>
        {s.price_text && <span className="flex items-center gap-1"><DollarSign className="h-3.5 w-3.5" /> {s.price_text}</span>}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Services</h1>
          <p className="text-sm text-muted-foreground">Manage the services your AI receptionist offers for booking</p>
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-4 w-4 mr-1" /> Add Service
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1,2,3].map(i => <Skeleton key={i} className="h-32 rounded-lg" />)}
        </div>
      ) : !services?.length ? (
        <div className="rounded-lg border p-12 text-center">
          <p className="text-muted-foreground">No services yet. Add your first service to get started.</p>
        </div>
      ) : groupedServices.length === 1 && groupedServices[0].key === "__all" ? (
        // No bot grouping needed — flat list
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {services.map(renderServiceCard)}
        </div>
      ) : (
        <div className="space-y-4">
          {groupedServices.map((group) => {
            const isOpen = !collapsedSections[group.key];
            const isUnassigned = group.key === "__unassigned";
            return (
              <Collapsible key={group.key} open={isOpen} onOpenChange={() => toggleSection(group.key)}>
                <CollapsibleTrigger asChild>
                  <button className="flex w-full items-center gap-3 rounded-lg border bg-muted/30 px-4 py-3 text-left transition-colors hover:bg-muted/50">
                    {isOpen ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                    {isUnassigned ? (
                      <Inbox className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <Bot className="h-4 w-4 text-muted-foreground" />
                    )}
                    <span className="font-medium text-sm">{group.label}</span>
                    {group.templateName && (
                      <Badge variant="secondary" className="text-xs font-normal">{group.templateName}</Badge>
                    )}
                    <span className="ml-auto text-xs text-muted-foreground">{group.items.length} service{group.items.length !== 1 ? "s" : ""}</span>
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 pt-3">
                    {group.items.map(renderServiceCard)}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            );
          })}
        </div>
      )}

      {/* Add Service Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add Service</DialogTitle></DialogHeader>
          <form onSubmit={(e) => { e.preventDefault(); addMutation.mutate(); }} className="space-y-4">
            <div className="space-y-2">
              <Label>Service Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Deep Tissue Massage" required />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Duration (minutes)</Label>
                <Input type="number" value={duration} onChange={(e) => setDuration(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label>Price</Label>
                <Input value={price} onChange={(e) => setPrice(e.target.value)} placeholder="$120" />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional description" />
            </div>
            <Button type="submit" className="w-full" disabled={addMutation.isPending}>
              {addMutation.isPending ? "Adding..." : "Add Service"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Service Dialog */}
      <Dialog open={!!editService} onOpenChange={(open) => !open && setEditService(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Service</DialogTitle>
            <DialogDescription>Update the details for this service</DialogDescription>
          </DialogHeader>
          <form onSubmit={(e) => { e.preventDefault(); updateMutation.mutate(); }} className="space-y-4">
            <div className="space-y-2">
              <Label>Service Name</Label>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} required />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Duration (minutes)</Label>
                <Input type="number" value={editDuration} onChange={(e) => setEditDuration(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label>Price</Label>
                <Input value={editPrice} onChange={(e) => setEditPrice(e.target.value)} placeholder="$120" />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} placeholder="Optional description" />
            </div>
            <div className="flex items-center justify-between">
              <Label>Active</Label>
              <Switch checked={editActive} onCheckedChange={setEditActive} />
            </div>
            <DialogFooter className="gap-2 sm:gap-0">
              <Button
                type="button"
                variant="destructive"
                onClick={() => { if (confirm("Delete this service?")) deleteMutation.mutate(editService.id); }}
              >
                Delete
              </Button>
              <Button type="submit" disabled={updateMutation.isPending}>
                {updateMutation.isPending ? "Saving..." : "Save Changes"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ServicesPage;
