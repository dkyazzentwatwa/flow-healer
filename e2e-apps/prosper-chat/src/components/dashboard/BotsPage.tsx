import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Copy, Plus, Pencil, Trash2, Bot } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PLANS } from "@/lib/plans";
import { industryTemplates } from "@/data/industryTemplates";

interface BotRow {
  id: string;
  business_id: string;
  name: string;
  widget_key: string;
  welcome_message: string | null;
  disclaimer_text: string | null;
  system_prompt: string | null;
  faq_ids: string[] | null;
  service_ids: string[] | null;
  is_active: boolean;
  template_id: string | null;
  created_at: string;
}

const BotsPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: bots = [], isLoading: botsLoading } = useQuery({
    queryKey: ["bots", business?.id],
    enabled: !!business?.id,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("bots")
        .select("*")
        .eq("business_id", business!.id)
        .order("created_at", { ascending: true });
      if (error) throw error;
      return data as BotRow[];
    },
  });

  const { data: subscription } = useQuery({
    queryKey: ["subscription", business?.id],
    enabled: !!business?.id,
    queryFn: async () => {
      const { data } = await supabase
        .from("subscriptions")
        .select("plan")
        .eq("business_id", business!.id)
        .maybeSingle();
      return data;
    },
  });

  const currentPlan = (subscription?.plan ?? "free") as keyof typeof PLANS;
  const botLimit = PLANS[currentPlan]?.limits.bots;
  const canAddBot = botLimit === null || bots.length < botLimit;

  const { data: allFaqs = [], refetch: refetchFaqs } = useQuery({
    queryKey: ["faqs", business?.id],
    enabled: !!business?.id,
    queryFn: async () => {
      const { data } = await supabase
        .from("faqs")
        .select("id, question")
        .eq("business_id", business!.id)
        .eq("is_active", true)
        .order("sort_order");
      return data || [];
    },
  });

  const { data: allServices = [], refetch: refetchServices } = useQuery({
    queryKey: ["services-for-bots", business?.id],
    enabled: !!business?.id,
    queryFn: async () => {
      const { data } = await supabase
        .from("services")
        .select("id, name")
        .eq("business_id", business!.id)
        .eq("is_active", true)
        .order("sort_order");
      return data || [];
    },
  });

  // Dialog state
  const [botDialogOpen, setBotDialogOpen] = useState(false);
  const [editingBot, setEditingBot] = useState<BotRow | null>(null);
  const [botName, setBotName] = useState("");
  const [botWelcome, setBotWelcome] = useState("");
  const [botDisclaimer, setBotDisclaimer] = useState("");
  const [botPrompt, setBotPrompt] = useState("");
  const [botFaqIds, setBotFaqIds] = useState<string[]>([]);
  const [botServiceIds, setBotServiceIds] = useState<string[]>([]);
  const [useAllFaqs, setUseAllFaqs] = useState(true);
  const [useAllServices, setUseAllServices] = useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingBot, setDeletingBot] = useState<BotRow | null>(null);

  const openBotDialog = (bot?: BotRow) => {
    if (bot) {
      setEditingBot(bot);
      setBotName(bot.name);
      setBotWelcome(bot.welcome_message || "");
      setBotDisclaimer(bot.disclaimer_text || "");
      setBotPrompt(bot.system_prompt || "");
      setUseAllFaqs(!bot.faq_ids);
      setBotFaqIds(bot.faq_ids || []);
      setUseAllServices(!bot.service_ids);
      setBotServiceIds(bot.service_ids || []);
      setSelectedTemplateId(bot.template_id || "");
    } else {
      setEditingBot(null);
      setBotName("");
      setBotWelcome("Hi! How can I help you today?");
      setBotDisclaimer("Please don't share sensitive personal, medical, or payment information here.");
      setBotPrompt("");
      setUseAllFaqs(true);
      setBotFaqIds([]);
      setUseAllServices(true);
      setBotServiceIds([]);
      setSelectedTemplateId("");
    }
    setBotDialogOpen(true);
  };

  const handleTemplateChange = (templateId: string) => {
    setSelectedTemplateId(templateId);
    if (templateId === "none") {
      setSelectedTemplateId("");
      return;
    }
    const tpl = industryTemplates.find((t) => t.id === templateId);
    if (!tpl) return;
    // Pre-fill bot name if empty
    if (!botName.trim()) setBotName(`${tpl.name} Bot`);
    // We'll auto-create FAQs/services on save, so set to "use all" for now
    setUseAllFaqs(true);
    setUseAllServices(true);
  };

  const saveBotMutation = useMutation({
    mutationFn: async () => {
      const tpl = selectedTemplateId
        ? industryTemplates.find((t) => t.id === selectedTemplateId)
        : null;

      let finalFaqIds = useAllFaqs ? null : botFaqIds;
      let finalServiceIds = useAllServices ? null : botServiceIds;

      // If a template is selected, auto-create missing FAQs and services
      if (tpl && business) {
        const createdFaqIds: string[] = [];
        const createdServiceIds: string[] = [];

        // Get existing FAQs/services to avoid duplicates
        const [{ data: existingFaqs }, { data: existingServices }] = await Promise.all([
          supabase.from("faqs").select("id, question").eq("business_id", business.id),
          supabase.from("services").select("id, name").eq("business_id", business.id),
        ]);

        const existingFaqQuestions = new Set((existingFaqs || []).map((f) => f.question.toLowerCase()));
        const existingServiceNames = new Set((existingServices || []).map((s) => s.name.toLowerCase()));

        // Create missing FAQs
        const newFaqs = tpl.faqs.filter((f) => !existingFaqQuestions.has(f.question.toLowerCase()));
        if (newFaqs.length > 0) {
          const { data: inserted } = await supabase
            .from("faqs")
            .insert(newFaqs.map((f, i) => ({
              business_id: business.id,
              question: f.question,
              answer: f.answer,
              sort_order: (existingFaqs?.length || 0) + i,
            })))
            .select("id");
          if (inserted) createdFaqIds.push(...inserted.map((r) => r.id));
        }

        // Create missing services
        const newServices = tpl.services.filter((s) => !existingServiceNames.has(s.name.toLowerCase()));
        if (newServices.length > 0) {
          const { data: inserted } = await supabase
            .from("services")
            .insert(newServices.map((s, i) => ({
              business_id: business.id,
              name: s.name,
              duration_minutes: s.duration_minutes,
              price_text: s.price_text,
              description: s.description || null,
              sort_order: (existingServices?.length || 0) + i,
            })))
            .select("id");
          if (inserted) createdServiceIds.push(...inserted.map((r) => r.id));
        }

        // Scope bot to template FAQs/services (both existing matches + newly created)
        const matchedFaqIds = (existingFaqs || [])
          .filter((f) => tpl.faqs.some((tf) => tf.question.toLowerCase() === f.question.toLowerCase()))
          .map((f) => f.id);
        const matchedServiceIds = (existingServices || [])
          .filter((s) => tpl.services.some((ts) => ts.name.toLowerCase() === s.name.toLowerCase()))
          .map((s) => s.id);

        finalFaqIds = [...matchedFaqIds, ...createdFaqIds];
        finalServiceIds = [...matchedServiceIds, ...createdServiceIds];

        // Refetch so the checkbox lists update
        await Promise.all([refetchFaqs(), refetchServices()]);
      }

      const payload = {
        business_id: business!.id,
        name: botName.trim() || "Bot",
        welcome_message: botWelcome || null,
        disclaimer_text: botDisclaimer || null,
        system_prompt: botPrompt || null,
        faq_ids: finalFaqIds as string[] | null,
        service_ids: finalServiceIds as string[] | null,
        template_id: selectedTemplateId || null,
      };

      if (editingBot) {
        const { error } = await supabase.from("bots").update(payload).eq("id", editingBot.id);
        if (error) throw error;
      } else {
        const { error } = await supabase.from("bots").insert(payload);
        if (error) throw error;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bots", business?.id] });
      setBotDialogOpen(false);
      toast({ title: editingBot ? "Bot updated" : "Bot created" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const toggleBotActive = async (bot: BotRow) => {
    await supabase.from("bots").update({ is_active: !bot.is_active }).eq("id", bot.id);
    queryClient.invalidateQueries({ queryKey: ["bots", business?.id] });
  };

  const confirmDeleteBot = async () => {
    if (!deletingBot) return;
    await supabase.from("bots").delete().eq("id", deletingBot.id);
    queryClient.invalidateQueries({ queryKey: ["bots", business?.id] });
    setDeleteDialogOpen(false);
    setDeletingBot(null);
    toast({ title: "Bot deleted" });
  };

  const getEmbedSnippet = (widgetKey: string) =>
    `<iframe src="${window.location.origin}/widget/${widgetKey}" style="position:fixed;bottom:0;right:0;width:400px;height:560px;border:none;z-index:9999;" allow="microphone"></iframe>`;

  const getTemplateName = (templateId: string | null) => {
    if (!templateId) return null;
    return industryTemplates.find((t) => t.id === templateId)?.name || null;
  };

  if (!business) {
    return (
      <div className="space-y-8 max-w-2xl">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl w-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Bot className="h-5 w-5" /> Bots
          </h1>
          <p className="text-sm text-muted-foreground">
            Each bot gets its own embed code, personality, and FAQ/service scope.
            {botLimit !== null && ` (${bots.length}/${botLimit} used)`}
          </p>
        </div>
        <Button size="sm" disabled={!canAddBot} onClick={() => openBotDialog()}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Add Bot
        </Button>
      </div>

      {!canAddBot && (
        <p className="text-xs text-destructive">
          You've reached the bot limit for your plan. Upgrade to add more.
        </p>
      )}

      {botsLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : bots.length === 0 ? (
        <div className="rounded-lg border p-8 text-center">
          <Bot className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
          <p className="text-sm text-muted-foreground">No bots yet — create one to get started.</p>
        </div>
      ) : (
        <div className="rounded-lg border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="hidden sm:table-cell">Template</TableHead>
                <TableHead className="hidden sm:table-cell">Widget Key</TableHead>
                <TableHead>Active</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bots.map((bot) => (
                <TableRow key={bot.id}>
                  <TableCell className="font-medium text-sm">{bot.name}</TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {getTemplateName(bot.template_id) ? (
                      <Badge variant="secondary" className="text-[10px]">{getTemplateName(bot.template_id)}</Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <code className="text-xs text-muted-foreground">{bot.widget_key}</code>
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={bot.is_active}
                      onCheckedChange={() => toggleBotActive(bot)}
                      disabled={bots.length === 1 && bot.is_active}
                    />
                  </TableCell>
                  <TableCell className="text-right space-x-1">
                    <Button size="icon" variant="ghost" onClick={() => openBotDialog(bot)} className="h-8 w-8">
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => {
                        navigator.clipboard.writeText(getEmbedSnippet(bot.widget_key));
                        toast({ title: "Embed code copied" });
                      }}
                      className="h-8 w-8"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      disabled={bots.length <= 1}
                      onClick={() => { setDeletingBot(bot); setDeleteDialogOpen(true); }}
                      className="h-8 w-8 text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Bot Edit Dialog */}
      <Dialog open={botDialogOpen} onOpenChange={setBotDialogOpen}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingBot ? "Edit Bot" : "Create Bot"}</DialogTitle>
            <DialogDescription>Configure this bot's personality, FAQs, and services scope.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {/* Template Picker */}
            <div className="space-y-1.5">
              <Label>Industry Template</Label>
              <Select value={selectedTemplateId || "none"} onValueChange={handleTemplateChange}>
                <SelectTrigger>
                  <SelectValue placeholder="No template" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No template</SelectItem>
                  {industryTemplates.map((tpl) => (
                    <SelectItem key={tpl.id} value={tpl.id}>
                      {tpl.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">
                Selecting a template will auto-create any missing FAQs & services and scope this bot to them.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>Bot Name</Label>
              <Input value={botName} onChange={(e) => setBotName(e.target.value)} placeholder="Sales Bot" />
            </div>
            <div className="space-y-1.5">
              <Label>Welcome Message</Label>
              <Textarea value={botWelcome} onChange={(e) => setBotWelcome(e.target.value)} placeholder="Hi! How can I help?" rows={2} />
            </div>
            <div className="space-y-1.5">
              <Label>Disclaimer</Label>
              <Input value={botDisclaimer} onChange={(e) => setBotDisclaimer(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Custom Personality Prompt <Badge variant="secondary" className="ml-1 text-[10px]">Optional</Badge></Label>
              <Textarea
                value={botPrompt}
                onChange={(e) => setBotPrompt(e.target.value)}
                placeholder="e.g. You are a cheerful sales assistant who loves exclamation marks!"
                rows={3}
              />
              <p className="text-[11px] text-muted-foreground">This is prepended to the default system prompt. Leave empty for default behavior.</p>
            </div>

            {/* FAQ Scope — hidden when template selected since it auto-scopes */}
            {!selectedTemplateId && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Checkbox id="use-all-faqs" checked={useAllFaqs} onCheckedChange={(v) => setUseAllFaqs(!!v)} />
                  <Label htmlFor="use-all-faqs" className="text-sm">Use all FAQs</Label>
                </div>
                {!useAllFaqs && allFaqs.length > 0 && (
                  <div className="ml-6 space-y-1.5 max-h-32 overflow-y-auto">
                    {allFaqs.map((faq) => (
                      <div key={faq.id} className="flex items-center gap-2">
                        <Checkbox
                          id={`faq-${faq.id}`}
                          checked={botFaqIds.includes(faq.id)}
                          onCheckedChange={(checked) => {
                            setBotFaqIds((prev) =>
                              checked ? [...prev, faq.id] : prev.filter((id) => id !== faq.id)
                            );
                          }}
                        />
                        <Label htmlFor={`faq-${faq.id}`} className="text-xs font-normal">{faq.question}</Label>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Service Scope — hidden when template selected */}
            {!selectedTemplateId && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Checkbox id="use-all-services" checked={useAllServices} onCheckedChange={(v) => setUseAllServices(!!v)} />
                  <Label htmlFor="use-all-services" className="text-sm">Use all services</Label>
                </div>
                {!useAllServices && allServices.length > 0 && (
                  <div className="ml-6 space-y-1.5 max-h-32 overflow-y-auto">
                    {allServices.map((svc) => (
                      <div key={svc.id} className="flex items-center gap-2">
                        <Checkbox
                          id={`svc-${svc.id}`}
                          checked={botServiceIds.includes(svc.id)}
                          onCheckedChange={(checked) => {
                            setBotServiceIds((prev) =>
                              checked ? [...prev, svc.id] : prev.filter((id) => id !== svc.id)
                            );
                          }}
                        />
                        <Label htmlFor={`svc-${svc.id}`} className="text-xs font-normal">{svc.name}</Label>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {selectedTemplateId && (
              <div className="rounded-md bg-secondary p-3 text-xs text-muted-foreground">
                <p className="font-medium text-foreground mb-1">Template will auto-configure:</p>
                <p>• {industryTemplates.find(t => t.id === selectedTemplateId)?.faqs.length || 0} FAQs</p>
                <p>• {industryTemplates.find(t => t.id === selectedTemplateId)?.services.length || 0} services</p>
                <p className="mt-1">Missing items will be created automatically. The bot will be scoped to only these items.</p>
              </div>
            )}

            {editingBot && (
              <div className="space-y-1.5">
                <Label>Embed Code</Label>
                <div className="rounded-md bg-secondary p-3 text-xs font-mono text-foreground overflow-x-auto break-all">
                  {getEmbedSnippet(editingBot.widget_key)}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBotDialogOpen(false)}>Cancel</Button>
            <Button onClick={() => saveBotMutation.mutate()} disabled={saveBotMutation.isPending || !botName.trim()}>
              {saveBotMutation.isPending ? "Saving..." : editingBot ? "Update Bot" : "Create Bot"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Bot</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{deletingBot?.name}"? This will break any embeds using its widget key.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmDeleteBot}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default BotsPage;
