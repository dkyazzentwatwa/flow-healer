import { serve } from "https://deno.land/std@0.190.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.57.2";
import { buildCorsHeaders } from "../_shared/cors.ts";
import { verifyWidgetToken } from "../_shared/widgetToken.ts";

const PLAN_LIMITS: Record<string, number | null> = {
  free: 50,
  pro: null,
  agency: null,
};

interface PromptContext {
  businessId?: string;
  name?: string;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  systemPrompt?: string | null;
  services: Array<{ name: string; duration_minutes: number; price_text: string | null }>;
  faqs: Array<{ question: string; answer: string }>;
}

async function loadPromptContext(widgetToken: string, supabaseAdmin: ReturnType<typeof createClient>): Promise<PromptContext> {
  const claims = await verifyWidgetToken(widgetToken);

  const [{ data: business }, { data: bot }, { data: allServices }, { data: allFaqs }] = await Promise.all([
    supabaseAdmin
      .from("businesses")
      .select("id, name, phone, email, address")
      .eq("id", claims.business_id)
      .single(),
    claims.bot_id
      ? supabaseAdmin
          .from("bots")
          .select("id, system_prompt, faq_ids, service_ids")
          .eq("id", claims.bot_id)
          .eq("business_id", claims.business_id)
          .eq("is_active", true)
          .maybeSingle()
      : Promise.resolve({ data: null as { id: string; system_prompt: string | null; faq_ids: string[] | null; service_ids: string[] | null } | null }),
    supabaseAdmin
      .from("services")
      .select("id, name, duration_minutes, price_text")
      .eq("business_id", claims.business_id)
      .eq("is_active", true)
      .order("sort_order"),
    supabaseAdmin
      .from("faqs")
      .select("id, question, answer")
      .eq("business_id", claims.business_id)
      .eq("is_active", true)
      .order("sort_order"),
  ]);

  if (!business) throw new Error("Business not found for widget");

  const services = bot?.service_ids?.length
    ? (allServices ?? []).filter((svc) => bot.service_ids!.includes(svc.id))
    : (allServices ?? []);

  const faqs = bot?.faq_ids?.length
    ? (allFaqs ?? []).filter((faq) => bot.faq_ids!.includes(faq.id))
    : (allFaqs ?? []);

  return {
    businessId: business.id,
    name: business.name,
    phone: business.phone,
    email: business.email,
    address: business.address,
    systemPrompt: bot?.system_prompt ?? null,
    services: services.map((svc) => ({
      name: svc.name,
      duration_minutes: svc.duration_minutes,
      price_text: svc.price_text,
    })),
    faqs: faqs.map((faq) => ({ question: faq.question, answer: faq.answer })),
  };
}

function buildSystemPrompt(context: PromptContext): string {
  const servicesBlock = context.services.length
    ? context.services.map((svc) => `- ${svc.name} (${svc.duration_minutes} min${svc.price_text ? `, ${svc.price_text}` : ""})`).join("\n")
    : "No services listed yet.";

  const faqsBlock = context.faqs.length
    ? context.faqs.map((faq) => `Q: ${faq.question}\nA: ${faq.answer}`).join("\n\n")
    : "";

  const contactBlock = [
    context.phone ? `Phone: ${context.phone}` : "",
    context.email ? `Email: ${context.email}` : "",
    context.address ? `Address: ${context.address}` : "",
  ].filter(Boolean).join("\n");

  const customPrompt = context.systemPrompt;
  if (customPrompt) {
    return `${customPrompt}

You are the virtual receptionist for ${context.name || "this business"}.

## Services Offered
${servicesBlock}

${faqsBlock ? `## Frequently Asked Questions\n${faqsBlock}` : ""}

${contactBlock ? `## Contact Information\n${contactBlock}` : ""}

## Rules
- Be warm, concise, and helpful. Use a friendly but professional tone.
- Answer questions using ONLY the information provided above. If you don't know something, say so and suggest they contact the business directly.
- Never make up prices, availability, or services not listed above.
- Keep responses short - 2-3 sentences max unless more detail is needed.`;
  }

  return `You are the friendly, professional virtual receptionist for ${context.name || "this business"}.

Your job is to help website visitors with questions, guide them toward booking appointments, and provide information about the business.

## Services Offered
${servicesBlock}

${faqsBlock ? `## Frequently Asked Questions\n${faqsBlock}` : ""}

${contactBlock ? `## Contact Information\n${contactBlock}` : ""}

## Rules
- Be warm, concise, and helpful. Use a friendly but professional tone.
- Answer questions using ONLY the information provided above. If you don't know something, say so and suggest they contact the business directly.
- Never make up prices, availability, or services not listed above.
- If someone wants to book, ask which service they're interested in and their preferred date/time. Then let them know someone will confirm.
- Keep responses short - 2-3 sentences max unless more detail is needed.
- You can use emoji sparingly for warmth.
- If asked about something outside the business scope, politely redirect.`;
}

serve(async (req) => {
  const corsHeaders = buildCorsHeaders(req, "*");
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { messages, businessContext } = await req.json();
    if (!Array.isArray(messages)) {
      return new Response(JSON.stringify({ error: { code: "bad_request", message: "messages must be an array" } }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const lovableApiKey = Deno.env.get("LOVABLE_API_KEY");
    if (!lovableApiKey) {
      throw new Error("LOVABLE_API_KEY is not configured");
    }

    const supabaseAdmin = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
      { auth: { persistSession: false } },
    );

    const widgetToken = typeof businessContext?.widgetToken === "string" ? businessContext.widgetToken : null;

    let promptContext: PromptContext = {
      businessId: undefined,
      name: businessContext?.name,
      phone: businessContext?.phone,
      email: businessContext?.email,
      address: businessContext?.address,
      systemPrompt: businessContext?.systemPrompt ?? null,
      services: Array.isArray(businessContext?.services) ? businessContext.services : [],
      faqs: Array.isArray(businessContext?.faqs) ? businessContext.faqs : [],
    };

    if (widgetToken) {
      promptContext = await loadPromptContext(widgetToken, supabaseAdmin);
    }

    if (promptContext.businessId) {
      const { data: sub } = await supabaseAdmin
        .from("subscriptions")
        .select("plan, current_period_start")
        .eq("business_id", promptContext.businessId)
        .maybeSingle();

      const plan = sub?.plan || "free";
      const limit = PLAN_LIMITS[plan];
      if (limit !== null) {
        const periodStart = sub?.current_period_start || new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString();
        const { count } = await supabaseAdmin
          .from("usage_records")
          .select("*", { count: "exact", head: true })
          .eq("business_id", promptContext.businessId)
          .eq("type", "chat")
          .gte("recorded_at", periodStart);

        if ((count || 0) >= limit) {
          return new Response(
            JSON.stringify({ error: { code: "plan_limit_reached", message: "This business has reached its monthly chat limit. Please upgrade your plan." } }),
            { status: 429, headers: { ...corsHeaders, "Content-Type": "application/json" } },
          );
        }
      }

      supabaseAdmin.from("usage_records").insert({ business_id: promptContext.businessId, type: "chat" }).then(() => {});
    }

    const response = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${lovableApiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "google/gemini-3-flash-preview",
        messages: [
          { role: "system", content: buildSystemPrompt(promptContext) },
          ...messages,
        ],
        stream: true,
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        return new Response(
          JSON.stringify({ error: { code: "provider_rate_limited", message: "AI service is busy. Please try again shortly." } }),
          { status: 429, headers: { ...corsHeaders, "Content-Type": "application/json" } },
        );
      }
      if (response.status === 402) {
        return new Response(
          JSON.stringify({ error: { code: "provider_unavailable", message: "AI service temporarily unavailable. Please try again later." } }),
          { status: 402, headers: { ...corsHeaders, "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({ error: { code: "provider_error", message: "Something went wrong. Please try again." } }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    return new Response(response.body, {
      headers: { ...corsHeaders, "Content-Type": "text/event-stream" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    const status = message.includes("token") ? 401 : 500;
    return new Response(
      JSON.stringify({ error: { code: status === 401 ? "unauthorized" : "internal_error", message } }),
      { status, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
