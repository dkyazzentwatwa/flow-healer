import { useState } from "react";
import { Link } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { useToast } from "@/hooks/use-toast";
import { industryTemplates, type IndustryTemplate } from "@/data/industryTemplates";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Briefcase, HelpCircle, Check, Plus, Loader2 } from "lucide-react";

function getErrorMessage(error: unknown, fallback: string): string {
  return typeof error === "object" && error && "message" in error && typeof error.message === "string"
    ? error.message
    : fallback;
}

const TemplatesPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const { toast } = useToast();
  const [preview, setPreview] = useState<IndustryTemplate | null>(null);
  const [applying, setApplying] = useState(false);

  const applyTemplate = async (template: IndustryTemplate) => {
    if (!business) return;
    setApplying(true);
    try {
      const { error: sErr } = await supabase.from("services").insert(
        template.services.map((s) => ({
          business_id: business.id,
          name: s.name,
          duration_minutes: s.duration_minutes,
          price_text: s.price_text,
          description: s.description || null,
        }))
      );
      if (sErr) throw sErr;

      const { error: fErr } = await supabase.from("faqs").insert(
        template.faqs.map((f) => ({
          business_id: business.id,
          question: f.question,
          answer: f.answer,
        }))
      );
      if (fErr) throw fErr;

      toast({ title: "Template applied!", description: `Added ${template.services.length} services and ${template.faqs.length} FAQs.` });
      setPreview(null);
    } catch (e: unknown) {
      toast({ title: "Error", description: getErrorMessage(e, "Could not apply template"), variant: "destructive" });
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Industry Templates</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Jumpstart your setup with a premade pack of services & FAQs, or{" "}
            <Link to="/dashboard/services" className="underline hover:text-foreground">create your own</Link>.
          </p>
        </div>
        <Badge variant="outline" className="gap-1">
          <Plus className="h-3 w-3" /> Custom
        </Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {industryTemplates.map((t) => (
          <Card
            key={t.id}
            className="cursor-pointer hover:border-foreground/30 transition-colors"
            onClick={() => setPreview(t)}
          >
            <CardHeader className="pb-3">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-secondary">
                  <t.icon className="h-4 w-4" />
                </div>
                <CardTitle className="text-base">{t.name}</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="flex gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1"><Briefcase className="h-3 w-3" />{t.services.length} services</span>
              <span className="flex items-center gap-1"><HelpCircle className="h-3 w-3" />{t.faqs.length} FAQs</span>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Preview dialog */}
      <Dialog open={!!preview} onOpenChange={() => setPreview(null)}>
        {preview && (
          <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <preview.icon className="h-5 w-5" /> {preview.name} Template
              </DialogTitle>
              <DialogDescription>
                This will add {preview.services.length} services and {preview.faqs.length} FAQs to your account.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
                  <Briefcase className="h-3.5 w-3.5" /> Services
                </h3>
                <div className="space-y-2">
                  {preview.services.map((s, i) => (
                    <div key={i} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                      <div>
                        <p className="font-medium">{s.name}</p>
                        <p className="text-xs text-muted-foreground">{s.duration_minutes} min</p>
                      </div>
                      <span className="text-xs font-mono">{s.price_text}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
                  <HelpCircle className="h-3.5 w-3.5" /> FAQs
                </h3>
                <div className="space-y-2">
                  {preview.faqs.map((f, i) => (
                    <div key={i} className="rounded-md border px-3 py-2 text-sm">
                      <p className="font-medium">{f.question}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{f.answer}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setPreview(null)}>Cancel</Button>
              <Button onClick={() => applyTemplate(preview)} disabled={applying}>
                {applying ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Check className="h-4 w-4 mr-1" />}
                Apply Template
              </Button>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
};

export default TemplatesPage;
