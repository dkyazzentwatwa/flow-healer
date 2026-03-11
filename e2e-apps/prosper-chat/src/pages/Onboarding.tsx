import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import {
  Building2, Phone, MapPin, ArrowRight, ArrowLeft, Check,
  Briefcase, HelpCircle, Code, MessageCircle, Copy, LayoutTemplate,
} from "lucide-react";
import { industryTemplates, type IndustryTemplate } from "@/data/industryTemplates";

const steps = ["Business Profile", "Add a Service", "Add a FAQ", "Embed Widget"];

function getErrorMessage(error: unknown, fallback: string): string {
  return typeof error === "object" && error && "message" in error && typeof error.message === "string"
    ? error.message
    : fallback;
}

const Onboarding = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [step, setStep] = useState(0);

  const { data: business } = useQuery({
    queryKey: ["first-business", user?.id],
    queryFn: async () => {
      const { data } = await supabase
        .from("businesses")
        .select("*")
        .eq("owner_id", user!.id)
        .order("created_at", { ascending: true })
        .limit(1)
        .single();
      return data;
    },
    enabled: !!user,
  });

  const [bizName, setBizName] = useState(business?.name || "");
  const [bizPhone, setBizPhone] = useState(business?.phone || "");
  const [bizAddress, setBizAddress] = useState(business?.address || "");

  const [svcName, setSvcName] = useState("");
  const [svcDuration, setSvcDuration] = useState("30");
  const [svcPrice, setSvcPrice] = useState("");

  const [faqQ, setFaqQ] = useState("");
  const [faqA, setFaqA] = useState("");

  const [saving, setSaving] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);

  const saveStep = async () => {
    if (!business) return;
    setSaving(true);
    try {
      if (step === 0) {
        const { error } = await supabase
          .from("businesses")
          .update({ name: bizName, phone: bizPhone, address: bizAddress })
          .eq("id", business.id);
        if (error) throw error;
      } else if (step === 1) {
        if (svcName.trim()) {
          const { error } = await supabase.from("services").insert({
            business_id: business.id,
            name: svcName,
            duration_minutes: parseInt(svcDuration) || 30,
            price_text: svcPrice,
          });
          if (error) throw error;
        }
      } else if (step === 2) {
        if (faqQ.trim() && faqA.trim()) {
          const { error } = await supabase.from("faqs").insert({
            business_id: business.id,
            question: faqQ,
            answer: faqA,
          });
          if (error) throw error;
        }
      } else if (step === 3) {
        const { error } = await supabase
          .from("businesses")
          .update({ onboarding_completed: true })
          .eq("id", business.id);
        if (error) throw error;
        await queryClient.invalidateQueries({ queryKey: ["first-business"] });
        navigate("/dashboard");
        return;
      }
      setStep((s) => s + 1);
    } catch (e: unknown) {
      toast({ title: "Error", description: getErrorMessage(e, "Could not save onboarding step"), variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const widgetSnippet = `<iframe src="${window.location.origin}/widget/${business?.widget_key || "..."}" style="position:fixed;bottom:0;right:0;width:400px;height:560px;border:none;z-index:9999;" allow="microphone"></iframe>`;

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg space-y-6">
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-foreground">
            <MessageCircle className="h-5 w-5 text-background" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">Set up your AI Receptionist</h1>
          <p className="mt-1 text-sm text-muted-foreground">Step {step + 1} of {steps.length}: {steps[step]}</p>
        </div>

        <div className="flex gap-1.5">
          {steps.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i <= step ? "bg-foreground" : "bg-border"
              }`}
            />
          ))}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="rounded-lg border p-6 space-y-4"
          >
            {step === 0 && (
              <>
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4" />
                  <h2 className="font-semibold text-sm">Business Profile</h2>
                </div>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label>Business Name</Label>
                    <Input value={bizName} onChange={(e) => setBizName(e.target.value)} placeholder="Glow Wellness Studio" required />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Phone</Label>
                    <Input value={bizPhone} onChange={(e) => setBizPhone(e.target.value)} placeholder="(555) 123-4567" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Address</Label>
                    <Input value={bizAddress} onChange={(e) => setBizAddress(e.target.value)} placeholder="123 Main St, Suite 4" />
                  </div>
                </div>
              </>
            )}

            {step === 1 && (
              <>
                <div className="flex items-center gap-2">
                  <Briefcase className="h-4 w-4" />
                  <h2 className="font-semibold text-sm">Add Your First Service</h2>
                </div>

                {showTemplates ? (
                  <>
                    <p className="text-sm text-muted-foreground">Pick an industry template to auto-fill services & FAQs:</p>
                    <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
                      {industryTemplates.map((t) => (
                        <button
                          key={t.id}
                          onClick={async () => {
                            if (!business) return;
                            setSaving(true);
                            try {
                              await supabase.from("services").insert(
                                t.services.map((s) => ({ business_id: business.id, name: s.name, duration_minutes: s.duration_minutes, price_text: s.price_text, description: s.description || null }))
                              );
                              await supabase.from("faqs").insert(
                                t.faqs.map((f) => ({ business_id: business.id, question: f.question, answer: f.answer }))
                              );
                              toast({ title: "Template applied!", description: `Added ${t.services.length} services and ${t.faqs.length} FAQs.` });
                              setStep(3);
                            } catch (e: unknown) {
                              toast({
                                title: "Error",
                                description: getErrorMessage(e, "Could not apply template"),
                                variant: "destructive",
                              });
                            } finally {
                              setSaving(false);
                            }
                          }}
                          className="flex items-center gap-2 rounded-md border p-3 text-left text-sm hover:border-foreground/30 transition-colors"
                        >
                          <t.icon className="h-4 w-4 shrink-0" />
                          <span className="font-medium">{t.name}</span>
                        </button>
                      ))}
                    </div>
                    <button onClick={() => setShowTemplates(false)} className="text-xs text-muted-foreground hover:text-foreground underline">
                      Or add a service manually
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => setShowTemplates(true)}
                      className="w-full flex items-center justify-center gap-2 rounded-md border border-dashed p-3 text-sm text-muted-foreground hover:border-foreground/30 hover:text-foreground transition-colors"
                    >
                      <LayoutTemplate className="h-4 w-4" /> Start from an industry template
                    </button>
                    <p className="text-sm text-muted-foreground">Or add one manually:</p>
                    <div className="space-y-3">
                      <div className="space-y-1.5">
                        <Label>Service Name</Label>
                        <Input value={svcName} onChange={(e) => setSvcName(e.target.value)} placeholder="Deep Tissue Massage" />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label>Duration (min)</Label>
                          <Input type="number" value={svcDuration} onChange={(e) => setSvcDuration(e.target.value)} />
                        </div>
                        <div className="space-y-1.5">
                          <Label>Price</Label>
                          <Input value={svcPrice} onChange={(e) => setSvcPrice(e.target.value)} placeholder="$120" />
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </>
            )}

            {step === 2 && (
              <>
                <div className="flex items-center gap-2">
                  <HelpCircle className="h-4 w-4" />
                  <h2 className="font-semibold text-sm">Add Your First FAQ</h2>
                </div>
                <p className="text-sm text-muted-foreground">What do customers commonly ask?</p>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label>Question</Label>
                    <Input value={faqQ} onChange={(e) => setFaqQ(e.target.value)} placeholder="What are your hours?" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Answer</Label>
                    <Textarea value={faqA} onChange={(e) => setFaqA(e.target.value)} placeholder="We're open Monday-Friday 9am-6pm..." rows={3} />
                  </div>
                </div>
              </>
            )}

            {step === 3 && (
              <>
                <div className="flex items-center gap-2">
                  <Code className="h-4 w-4" />
                  <h2 className="font-semibold text-sm">Embed Your Widget</h2>
                </div>
                <p className="text-sm text-muted-foreground">
                  Add this snippet to your website. You can also do this later from Settings.
                </p>
                <div className="rounded-md bg-secondary p-4 text-xs font-mono text-foreground overflow-x-auto break-all">
                  {widgetSnippet}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    navigator.clipboard.writeText(widgetSnippet);
                    toast({ title: "Copied!" });
                  }}
                >
                  <Copy className="h-3.5 w-3.5 mr-1" /> Copy Code
                </Button>
                <div className="rounded-md border p-4">
                  <div className="flex items-start gap-3">
                    <Check className="h-4 w-4 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium">You're all set!</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Click "Go to Dashboard" to manage your services, FAQs, leads, and appointments.
                      </p>
                    </div>
                  </div>
                </div>
              </>
            )}
          </motion.div>
        </AnimatePresence>

        <div className="flex items-center justify-between">
          {step > 0 ? (
            <Button variant="ghost" onClick={() => setStep((s) => s - 1)} disabled={saving}>
              <ArrowLeft className="h-4 w-4 mr-1" /> Back
            </Button>
          ) : (
            <div />
          )}
          <Button onClick={saveStep} disabled={saving}>
            {saving ? "Saving..." : step === 3 ? "Go to Dashboard" : "Continue"}
            {step < 3 && <ArrowRight className="h-4 w-4 ml-1" />}
          </Button>
        </div>

        {(step === 1 || step === 2) && (
          <p className="text-center">
            <button
              onClick={() => setStep((s) => s + 1)}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              Skip for now
            </button>
          </p>
        )}
      </div>
    </div>
  );
};

export default Onboarding;
