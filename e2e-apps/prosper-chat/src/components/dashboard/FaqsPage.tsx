import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Plus, Trash2, ChevronDown, ChevronRight, Bot, Inbox } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { industryTemplates } from "@/data/industryTemplates";
import type { Tables } from "@/integrations/supabase/types";

const FaqsPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");

  // Edit modal state
  const [editFaq, setEditFaq] = useState<Tables<"faqs"> | null>(null);
  const [editQuestion, setEditQuestion] = useState("");
  const [editAnswer, setEditAnswer] = useState("");
  const [editActive, setEditActive] = useState(true);

  // Collapsed sections state
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  const toggleSection = (key: string) => {
    setCollapsedSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const openEdit = (faq: Tables<"faqs">) => {
    setEditFaq(faq);
    setEditQuestion(faq.question);
    setEditAnswer(faq.answer);
    setEditActive(faq.is_active ?? true);
  };

  const { data: faqs, isLoading } = useQuery({
    queryKey: ["faqs", business?.id],
    queryFn: async () => {
      const { data } = await supabase.from("faqs").select("*").eq("business_id", business!.id).order("sort_order");
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

  // Group FAQs by bot
  const groupedFaqs = useMemo(() => {
    if (!faqs || !bots) return [];

    const groups: { key: string; label: string; templateName?: string; items: typeof faqs }[] = [];
    const assigned = new Set<string>();

    for (const bot of bots) {
      if (!bot.faq_ids?.length) continue;
      const scopedIds = new Set(bot.faq_ids as string[]);
      const items = faqs.filter(f => scopedIds.has(f.id));
      if (!items.length) continue;
      items.forEach(f => assigned.add(f.id));

      const tpl = bot.template_id ? industryTemplates.find(t => t.id === bot.template_id) : null;
      groups.push({
        key: bot.id,
        label: bot.name,
        templateName: tpl?.name,
        items,
      });
    }

    const unassigned = faqs.filter(f => !assigned.has(f.id));
    if (unassigned.length) {
      groups.push({ key: "__unassigned", label: "Shared / Unassigned", items: unassigned });
    }

    if (groups.length === 0) {
      groups.push({ key: "__all", label: "All FAQs", items: faqs });
    }

    return groups;
  }, [faqs, bots]);

  const addMutation = useMutation({
    mutationFn: async () => {
      const { error } = await supabase.from("faqs").insert({ business_id: business!.id, question, answer });
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["faqs"] });
      setShowAdd(false);
      setQuestion(""); setAnswer("");
      toast({ title: "FAQ added" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editFaq) return;
      const { error } = await supabase.from("faqs").update({
        question: editQuestion,
        answer: editAnswer,
        is_active: editActive,
      }).eq("id", editFaq.id);
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["faqs"] });
      setEditFaq(null);
      toast({ title: "FAQ updated" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from("faqs").delete().eq("id", id);
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["faqs"] });
      setEditFaq(null);
      toast({ title: "FAQ deleted" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const renderFaqCard = (faq: Tables<"faqs">) => (
    <div
      key={faq.id}
      onClick={() => openEdit(faq)}
      className={`group rounded-lg border p-5 transition-colors hover:bg-secondary/30 cursor-pointer ${!faq.is_active ? "opacity-50" : ""}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium">{faq.question}</h3>
          <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{faq.answer}</p>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); if (confirm("Delete this FAQ?")) deleteMutation.mutate(faq.id); }}
          className="ml-2 text-muted-foreground/40 hover:text-destructive transition-colors opacity-0 group-hover:opacity-100"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">FAQs</h1>
          <p className="text-sm text-muted-foreground">Knowledge base for your AI receptionist</p>
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-4 w-4 mr-1" /> Add FAQ
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <Skeleton key={i} className="h-20 rounded-lg" />)}
        </div>
      ) : !faqs?.length ? (
        <div className="rounded-lg border p-12 text-center">
          <p className="text-muted-foreground">No FAQs yet. Add common questions your visitors ask.</p>
        </div>
      ) : groupedFaqs.length === 1 && groupedFaqs[0].key === "__all" ? (
        // No bot grouping needed — flat list
        <div className="space-y-3">
          {faqs.map(renderFaqCard)}
        </div>
      ) : (
        <div className="space-y-4">
          {groupedFaqs.map((group) => {
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
                    <span className="ml-auto text-xs text-muted-foreground">{group.items.length} FAQ{group.items.length !== 1 ? "s" : ""}</span>
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="space-y-3 pt-3">
                    {group.items.map(renderFaqCard)}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            );
          })}
        </div>
      )}

      {/* Add FAQ Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add FAQ</DialogTitle></DialogHeader>
          <form onSubmit={(e) => { e.preventDefault(); addMutation.mutate(); }} className="space-y-4">
            <div className="space-y-2">
              <Label>Question</Label>
              <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What are your hours?" required />
            </div>
            <div className="space-y-2">
              <Label>Answer</Label>
              <Textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="We're open Monday–Friday..." required />
            </div>
            <Button type="submit" className="w-full" disabled={addMutation.isPending}>
              {addMutation.isPending ? "Adding..." : "Add FAQ"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit FAQ Dialog */}
      <Dialog open={!!editFaq} onOpenChange={(open) => !open && setEditFaq(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit FAQ</DialogTitle>
            <DialogDescription>Update this question and answer</DialogDescription>
          </DialogHeader>
          <form onSubmit={(e) => { e.preventDefault(); updateMutation.mutate(); }} className="space-y-4">
            <div className="space-y-2">
              <Label>Question</Label>
              <Input value={editQuestion} onChange={(e) => setEditQuestion(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label>Answer</Label>
              <Textarea value={editAnswer} onChange={(e) => setEditAnswer(e.target.value)} required />
            </div>
            <div className="flex items-center justify-between">
              <Label>Active</Label>
              <Switch checked={editActive} onCheckedChange={setEditActive} />
            </div>
            <DialogFooter className="gap-2 sm:gap-0">
              <Button
                type="button"
                variant="destructive"
                onClick={() => { if (confirm("Delete this FAQ?")) deleteMutation.mutate(editFaq.id); }}
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

export default FaqsPage;
