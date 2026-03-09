import { serve } from "https://deno.land/std@0.190.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.57.2";
import { buildCorsHeaders } from "../_shared/cors.ts";
import { signWidgetToken } from "../_shared/widgetToken.ts";

interface BotRow {
  id: string;
  business_id: string;
  widget_key: string;
  welcome_message: string | null;
  disclaimer_text: string | null;
  system_prompt: string | null;
  faq_ids: string[] | null;
  service_ids: string[] | null;
}

serve(async (req) => {
  const corsHeaders = buildCorsHeaders(req, "*");
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: { code: "method_not_allowed", message: "Only POST is supported" } }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  try {
    const { widget_key } = await req.json();
    if (typeof widget_key !== "string" || widget_key.trim().length < 5) {
      return new Response(JSON.stringify({ error: { code: "invalid_widget_key", message: "widget_key is required" } }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const supabaseAdmin = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
      { auth: { persistSession: false } },
    );

    const normalizedWidgetKey = widget_key.trim();

    const { data: botRow } = await supabaseAdmin
      .from("bots")
      .select("id, business_id, widget_key, welcome_message, disclaimer_text, system_prompt, faq_ids, service_ids")
      .eq("widget_key", normalizedWidgetKey)
      .eq("is_active", true)
      .maybeSingle<BotRow>();

    let businessId: string;
    let bot: BotRow | null = null;

    if (botRow) {
      businessId = botRow.business_id;
      bot = botRow;
    } else {
      const { data: businessByWidget } = await supabaseAdmin
        .from("businesses")
        .select("id, widget_key")
        .eq("widget_key", normalizedWidgetKey)
        .maybeSingle();

      if (!businessByWidget) {
        return new Response(JSON.stringify({ error: { code: "widget_not_found", message: "Widget not found" } }), {
          status: 404,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      businessId = businessByWidget.id;
    }

    const [{ data: business }, { data: allFaqs }, { data: allServices }, { data: calendlySetting }] = await Promise.all([
      supabaseAdmin
        .from("businesses")
        .select("id, name, phone, email, address, widget_key")
        .eq("id", businessId)
        .single(),
      supabaseAdmin
        .from("faqs")
        .select("id, question, answer")
        .eq("business_id", businessId)
        .eq("is_active", true)
        .order("sort_order"),
      supabaseAdmin
        .from("services")
        .select("id, name, duration_minutes, price_text")
        .eq("business_id", businessId)
        .eq("is_active", true)
        .order("sort_order"),
      supabaseAdmin
        .from("business_settings")
        .select("value")
        .eq("business_id", businessId)
        .eq("key", "calendly_url")
        .maybeSingle(),
    ]);

    if (!business) {
      return new Response(JSON.stringify({ error: { code: "business_not_found", message: "Business not found" } }), {
        status: 404,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const faqs = bot?.faq_ids?.length
      ? (allFaqs ?? []).filter((faq) => bot!.faq_ids!.includes(faq.id))
      : (allFaqs ?? []);

    const services = bot?.service_ids?.length
      ? (allServices ?? []).filter((svc) => bot!.service_ids!.includes(svc.id))
      : (allServices ?? []);

    const widgetToken = await signWidgetToken({
      business_id: business.id,
      bot_id: bot?.id,
      widget_key: normalizedWidgetKey,
      exp: Math.floor(Date.now() / 1000) + (60 * 60 * 24),
    });

    return new Response(JSON.stringify({
      widget_token: widgetToken,
      bot: bot
        ? {
            id: bot.id,
            welcome_message: bot.welcome_message,
            disclaimer_text: bot.disclaimer_text,
            system_prompt: bot.system_prompt,
          }
        : null,
      business: {
        id: business.id,
        name: business.name,
        phone: business.phone,
        email: business.email,
        address: business.address,
      },
      faqs: faqs.map((faq) => ({ question: faq.question, answer: faq.answer })),
      services: services.map((svc) => ({ id: svc.id, name: svc.name, duration_minutes: svc.duration_minutes, price_text: svc.price_text })),
      calendly_url: calendlySetting?.value ? String(calendlySetting.value) : null,
    }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return new Response(JSON.stringify({ error: { code: "internal_error", message } }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
