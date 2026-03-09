import { serve } from "https://deno.land/std@0.190.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.57.2";
import { buildCorsHeaders } from "../_shared/cors.ts";
import { verifyWidgetToken } from "../_shared/widgetToken.ts";

serve(async (req) => {
  const corsHeaders = buildCorsHeaders(req, "*");
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { widget_token, service_id, start_time, name, email, phone } = await req.json();
    if (!widget_token || !service_id || !start_time || !name || !email) {
      return new Response(
        JSON.stringify({ error: { code: "bad_request", message: "Missing required fields (widget_token, service_id, start_time, name, email)" } }),
        {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    const claims = await verifyWidgetToken(String(widget_token));
    const businessId = claims.business_id;

    const startDate = new Date(start_time);
    if (Number.isNaN(startDate.getTime())) {
      return new Response(JSON.stringify({ error: { code: "invalid_start_time", message: "start_time must be a valid ISO timestamp" } }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    if (startDate.getTime() < Date.now() - 60_000) {
      return new Response(JSON.stringify({ error: { code: "invalid_start_time", message: "Appointment time must be in the future" } }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
      { auth: { persistSession: false } },
    );

    const { data: service, error: serviceError } = await supabase
      .from("services")
      .select("duration_minutes, name")
      .eq("id", service_id)
      .eq("business_id", businessId)
      .eq("is_active", true)
      .single();

    if (serviceError || !service) {
      return new Response(JSON.stringify({ error: { code: "service_not_found", message: "Service not found" } }), {
        status: 404,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const { data: business } = await supabase
      .from("businesses")
      .select("buffer_minutes")
      .eq("id", businessId)
      .single();

    const endDate = new Date(startDate.getTime() + service.duration_minutes * 60 * 1000);
    const bufferMinutes = business?.buffer_minutes || 15;
    const bufferMs = bufferMinutes * 60 * 1000;

    const checkStart = new Date(startDate.getTime() - bufferMs);
    const checkEnd = new Date(endDate.getTime() + bufferMs);

    const { data: conflicts } = await supabase
      .from("appointments")
      .select("id")
      .eq("business_id", businessId)
      .in("status", ["pending", "confirmed"])
      .lt("start_time", checkEnd.toISOString())
      .gt("end_time", checkStart.toISOString());

    if (conflicts && conflicts.length > 0) {
      return new Response(
        JSON.stringify({ error: { code: "time_conflict", message: "This time slot is no longer available. Please choose another time." } }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const normalizedEmail = String(email).trim().toLowerCase();
    const { data: existingLead } = await supabase
      .from("leads")
      .select("id")
      .eq("business_id", businessId)
      .eq("email", normalizedEmail)
      .maybeSingle();

    let leadId: string;
    let isNewLead = false;

    if (existingLead) {
      leadId = existingLead.id;
      await supabase
        .from("leads")
        .update({ first_name: String(name).trim(), phone: phone ? String(phone).trim() : null, is_returning: true })
        .eq("id", leadId);
    } else {
      const { data: newLead, error: leadError } = await supabase
        .from("leads")
        .insert({
          business_id: businessId,
          first_name: String(name).trim(),
          email: normalizedEmail,
          phone: phone ? String(phone).trim() : null,
          source: "widget_booking",
          status: "new",
        })
        .select("id")
        .single();

      if (leadError || !newLead) {
        return new Response(JSON.stringify({ error: { code: "lead_create_failed", message: "Failed to create lead record" } }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      leadId = newLead.id;
      isNewLead = true;
    }

    const { data: appointment, error: appointmentError } = await supabase
      .from("appointments")
      .insert({
        business_id: businessId,
        service_id,
        lead_id: leadId,
        start_time: startDate.toISOString(),
        end_time: endDate.toISOString(),
        status: "pending",
        notes: `Booked via widget: ${service.name}`,
      })
      .select("id, start_time, end_time")
      .single();

    if (appointmentError || !appointment) {
      return new Response(JSON.stringify({ error: { code: "appointment_create_failed", message: "Failed to create appointment" } }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const usageWrites = [
      supabase.from("usage_records").insert({ business_id: businessId, type: "appointment_booked" }),
    ];
    if (isNewLead) {
      usageWrites.push(supabase.from("usage_records").insert({ business_id: businessId, type: "lead_captured" }));
    }
    Promise.allSettled(usageWrites).then(() => {});

    return new Response(
      JSON.stringify({
        success: true,
        appointment_id: appointment.id,
        service_name: service.name,
        start_time: appointment.start_time,
        end_time: appointment.end_time,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    const status = message.includes("token") ? 401 : 500;
    return new Response(
      JSON.stringify({ error: { code: status === 401 ? "unauthorized" : "internal_error", message } }),
      { status, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
