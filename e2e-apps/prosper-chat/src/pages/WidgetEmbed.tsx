import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ChatWidget from "@/components/chat/ChatWidget";

interface WidgetBootstrapResponse {
  widget_token: string;
  bot: {
    id: string;
    welcome_message: string | null;
    disclaimer_text: string | null;
    system_prompt: string | null;
  } | null;
  business: {
    id: string;
    name: string;
    phone: string | null;
    email: string | null;
    address: string | null;
  };
  faqs: { question: string; answer: string }[];
  services: { id: string; name: string; duration_minutes: number; price_text: string | null }[];
  calendly_url: string | null;
}

const WIDGET_BOOTSTRAP_URL = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/widget-bootstrap`;

const WidgetEmbed = () => {
  const { widgetKey } = useParams<{ widgetKey: string }>();
  const [widgetData, setWidgetData] = useState<WidgetBootstrapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      if (!widgetKey) {
        setError("No widget key");
        return;
      }

      try {
        const resp = await fetch(WIDGET_BOOTSTRAP_URL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
          },
          body: JSON.stringify({ widget_key: widgetKey }),
        });

        const data = await resp.json();
        if (!resp.ok) {
          setError(data?.error?.message || "Widget not found");
          return;
        }

        setWidgetData(data as WidgetBootstrapResponse);
      } catch {
        setError("Could not load widget");
      }
    };

    load();
  }, [widgetKey]);

  if (error) return <div className="flex h-screen items-center justify-center text-muted-foreground text-sm">{error}</div>;
  if (!widgetData) return <div className="flex h-screen items-center justify-center"><div className="h-6 w-6 animate-spin rounded-full border-2 border-foreground border-t-transparent" /></div>;

  return (
    <div className="h-screen w-screen bg-transparent">
      <ChatWidget
        embedded
        botId={widgetData.bot?.id}
        businessId={widgetData.business.id}
        businessName={widgetData.business.name}
        welcomeMessage={widgetData.bot?.welcome_message || undefined}
        disclaimerText={widgetData.bot?.disclaimer_text || undefined}
        systemPrompt={widgetData.bot?.system_prompt || undefined}
        businessPhone={widgetData.business.phone || undefined}
        businessEmail={widgetData.business.email || undefined}
        businessAddress={widgetData.business.address || undefined}
        faqs={widgetData.faqs}
        services={widgetData.services}
        calendlyUrl={widgetData.calendly_url || undefined}
        widgetToken={widgetData.widget_token}
      />
    </div>
  );
};

export default WidgetEmbed;
