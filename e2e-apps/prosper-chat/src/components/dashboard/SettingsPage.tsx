import { useState, useEffect, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";
import { Moon, Sun, Calendar, Loader2, Check, Unlink, ExternalLink } from "lucide-react";

const TIMEZONES = [
  "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
  "America/Phoenix", "America/Anchorage", "Pacific/Honolulu", "America/Toronto",
  "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Tokyo", "Asia/Shanghai",
  "Australia/Sydney",
];

const SettingsPage = () => {
  const { activeBusiness: business, refetchBusinesses } = useActiveBusiness();
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [timezone, setTimezone] = useState("America/New_York");
  const [escalationEmail, setEscalationEmail] = useState("");
  const [escalationPhone, setEscalationPhone] = useState("");
  const [storeTranscripts, setStoreTranscripts] = useState(false);
  const [retentionDays, setRetentionDays] = useState("30");
  const [darkMode, setDarkMode] = useState(() =>
    document.documentElement.classList.contains("dark")
  );
  const [calendlyUrl, setCalendlyUrl] = useState("");
  const [calendlySaving, setCalendlySaving] = useState(false);
  const [calendlyLoaded, setCalendlyLoaded] = useState(false);

  const toggleDarkMode = useCallback((checked: boolean) => {
    setDarkMode(checked);
    document.documentElement.classList.toggle("dark", checked);
    localStorage.setItem("theme", checked ? "dark" : "light");
  }, []);

  // Load Calendly URL from business_settings
  useEffect(() => {
    if (!business) return;
    const loadCalendly = async () => {
      const { data } = await supabase
        .from("business_settings")
        .select("value")
        .eq("business_id", business.id)
        .eq("key", "calendly_url")
        .maybeSingle();
      if (data?.value) {
        setCalendlyUrl(data.value as string);
      }
      setCalendlyLoaded(true);
    };
    loadCalendly();
  }, [business]);

  const saveCalendlyUrl = async () => {
    if (!business) return;
    setCalendlySaving(true);
    try {
      const trimmed = calendlyUrl.trim();
      if (trimmed) {
        await supabase
          .from("business_settings")
          .upsert(
            { business_id: business.id, key: "calendly_url", value: trimmed },
            { onConflict: "business_id,key" }
          );
      } else {
        await supabase
          .from("business_settings")
          .delete()
          .eq("business_id", business.id)
          .eq("key", "calendly_url");
      }
      toast({ title: trimmed ? "Calendly URL saved" : "Calendly disconnected" });
    } catch {
      toast({ title: "Error saving Calendly URL", variant: "destructive" });
    } finally {
      setCalendlySaving(false);
    }
  };

  useEffect(() => {
    if (business) {
      setName(business.name);
      setPhone(business.phone || "");
      setEmail(business.email || "");
      setAddress(business.address || "");
      setTimezone(business.timezone || "America/New_York");
      setEscalationEmail(business.escalation_email || "");
      setEscalationPhone(business.escalation_phone || "");
      setStoreTranscripts(business.privacy_store_transcripts || false);
      setRetentionDays(String(business.privacy_retention_days || 30));
    }
  }, [business]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const { error } = await supabase
        .from("businesses")
        .update({
          name,
          phone: phone || null,
          email: email || null,
          address: address || null,
          timezone,
          escalation_email: escalationEmail || null,
          escalation_phone: escalationPhone || null,
          privacy_store_transcripts: storeTranscripts,
          privacy_retention_days: parseInt(retentionDays),
        })
        .eq("id", business!.id);
      if (error) throw error;
    },
    onSuccess: async () => {
      await refetchBusinesses();
      toast({ title: "Settings saved" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  if (!business) {
    return (
      <div className="space-y-8 max-w-2xl">
        <div><Skeleton className="h-8 w-40" /><Skeleton className="h-4 w-64 mt-2" /></div>
        <Skeleton className="h-48 w-full rounded-lg" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-2xl w-full">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Configure your business and widget preferences</p>
      </div>

      <section className="rounded-lg border p-4 md:p-6 space-y-4">
        <h2 className="text-sm font-medium">Business Profile</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="text-sm text-muted-foreground">Business Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">Email</label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1" placeholder="hello@yourbusiness.com" />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">Phone</label>
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">Timezone</label>
            <Select value={timezone} onValueChange={setTimezone}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                {TIMEZONES.map((tz) => (
                  <SelectItem key={tz} value={tz}>{tz.replace(/_/g, " ")}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="sm:col-span-2">
            <label className="text-sm text-muted-foreground">Address</label>
            <Input value={address} onChange={(e) => setAddress(e.target.value)} className="mt-1" />
          </div>
        </div>
      </section>



      <section className="rounded-lg border p-4 md:p-6 space-y-4">
        <h2 className="text-sm font-medium">Appearance</h2>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {darkMode ? <Moon className="h-4 w-4 text-muted-foreground" /> : <Sun className="h-4 w-4 text-muted-foreground" />}
            <div>
              <p className="text-sm">Dark mode</p>
              <p className="text-xs text-muted-foreground">Toggle between light and dark theme</p>
            </div>
          </div>
          <Switch checked={darkMode} onCheckedChange={toggleDarkMode} />
        </div>
      </section>

      <section className="rounded-lg border p-4 md:p-6 space-y-4">
        <h2 className="text-sm font-medium">Calendly Integration</h2>
        <p className="text-xs text-muted-foreground">
          Paste your Calendly URL so visitors can book appointments directly from the chat widget.
        </p>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <p className="text-sm">
              {!calendlyLoaded ? "Loading…" : calendlyUrl.trim() ? "Connected" : "Not connected"}
            </p>
          </div>
          <Input
            value={calendlyUrl}
            onChange={(e) => setCalendlyUrl(e.target.value)}
            placeholder="https://calendly.com/your-name"
            className="text-sm"
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={saveCalendlyUrl} disabled={calendlySaving}>
              {calendlySaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
              Save
            </Button>
            {calendlyUrl.trim() && (
              <Button size="sm" variant="outline" asChild>
                <a href={calendlyUrl.trim()} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> Preview
                </a>
              </Button>
            )}
          </div>
        </div>
      </section>

      <section className="rounded-lg border p-4 md:p-6 space-y-4">
        <h2 className="text-sm font-medium">Escalation Contacts</h2>
        <p className="text-xs text-muted-foreground">Where should the AI direct visitors who need human assistance?</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="text-sm text-muted-foreground">Escalation Email</label>
            <Input type="email" value={escalationEmail} onChange={(e) => setEscalationEmail(e.target.value)} className="mt-1" placeholder="support@yourbusiness.com" />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">Escalation Phone</label>
            <Input value={escalationPhone} onChange={(e) => setEscalationPhone(e.target.value)} className="mt-1" placeholder="(555) 123-4567" />
          </div>
        </div>
      </section>

      <section className="rounded-lg border p-4 md:p-6 space-y-4">
        <h2 className="text-sm font-medium">Privacy & Retention</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm">Store chat transcripts</p>
            <p className="text-xs text-muted-foreground">If enabled, transcripts are redacted and auto-deleted after {retentionDays} days.</p>
          </div>
          <Switch checked={storeTranscripts} onCheckedChange={setStoreTranscripts} />
        </div>
        {storeTranscripts && (
          <div>
            <label className="text-sm text-muted-foreground">Retention period (days)</label>
            <Input type="number" value={retentionDays} onChange={(e) => setRetentionDays(e.target.value)} className="mt-1 w-32" />
          </div>
        )}
      </section>

      <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
        {saveMutation.isPending ? "Saving..." : "Save Settings"}
      </Button>
    </div>
  );
};

export default SettingsPage;
