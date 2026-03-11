import { serve } from "https://deno.land/std@0.190.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.57.2";
import { buildCorsHeaders } from "../_shared/cors.ts";
import { verifyWidgetToken } from "../_shared/widgetToken.ts";

const DAY_MAP: Record<string, string> = {
  Sun: "sun",
  Mon: "mon",
  Tue: "tue",
  Wed: "wed",
  Thu: "thu",
  Fri: "fri",
  Sat: "sat",
};

function getZonedDateParts(date: Date, timeZone: string): { year: number; month: number; day: number; hour: number; minute: number; weekday: string } {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
    hour12: false,
  });

  const parts = formatter.formatToParts(date);
  const values: Record<string, string> = {};
  for (const part of parts) {
    if (part.type !== "literal") values[part.type] = part.value;
  }

  return {
    year: Number(values.year),
    month: Number(values.month),
    day: Number(values.day),
    hour: Number(values.hour),
    minute: Number(values.minute),
    weekday: values.weekday,
  };
}

function getTimeZoneOffsetMs(date: Date, timeZone: string): number {
  const zoned = getZonedDateParts(date, timeZone);
  const utcEquivalent = Date.UTC(zoned.year, zoned.month - 1, zoned.day, zoned.hour, zoned.minute, 0);
  return utcEquivalent - date.getTime();
}

function zonedDateTimeToUtc(date: string, time: string, timeZone: string): Date {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const guess = new Date(Date.UTC(year, month - 1, day, hour, minute, 0));
  const offset = getTimeZoneOffsetMs(guess, timeZone);
  return new Date(guess.getTime() - offset);
}

function formatDate(date: Date, timeZone: string): string {
  const parts = getZonedDateParts(date, timeZone);
  return `${parts.year}-${parts.month.toString().padStart(2, "0")}-${parts.day.toString().padStart(2, "0")}`;
}

function nextDate(date: string): string {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + 1);
  return value.toISOString().slice(0, 10);
}

function listBookableSlots({
  date,
  timeZone,
  businessHours,
  bufferMinutes,
  durationMinutes,
  appointments,
  now = new Date(),
}: {
  date: string;
  timeZone: string;
  businessHours: Record<string, { open: string; close: string } | null> | null;
  bufferMinutes: number;
  durationMinutes: number;
  appointments: Array<{ start_time: string; end_time: string }>;
  now?: Date;
}): { slots: string[]; closedMessage?: string } {
  const requestWeekday = getZonedDateParts(zonedDateTimeToUtc(date, "12:00", timeZone), timeZone).weekday;
  const dayKey = DAY_MAP[requestWeekday];
  const dayHours = dayKey ? businessHours?.[dayKey] : null;

  if (!dayHours) {
    return { slots: [], closedMessage: "Business is closed on this day" };
  }

  const [openH, openM] = dayHours.open.split(":").map(Number);
  const [closeH, closeM] = dayHours.close.split(":").map(Number);
  const openMin = openH * 60 + openM;
  const closeMin = closeH * 60 + closeM;

  const booked = appointments.map((apt) => {
    const localStart = getZonedDateParts(new Date(apt.start_time), timeZone);
    const localEnd = getZonedDateParts(new Date(apt.end_time), timeZone);
    return {
      startMin: localStart.hour * 60 + localStart.minute,
      endMin: localEnd.hour * 60 + localEnd.minute,
    };
  });

  const interval = Math.min(30, durationMinutes);
  const slots: string[] = [];

  for (let slotStart = openMin; slotStart + durationMinutes <= closeMin; slotStart += interval) {
    const slotEnd = slotStart + durationMinutes + bufferMinutes;

    const hasConflict = booked.some((entry) => {
      const entryEnd = entry.endMin + bufferMinutes;
      return slotStart < entryEnd && slotEnd > entry.startMin;
    });

    if (!hasConflict) {
      const hour = Math.floor(slotStart / 60);
      const minute = slotStart % 60;
      slots.push(`${hour.toString().padStart(2, "0")}:${minute.toString().padStart(2, "0")}`);
    }
  }

  const todayInTz = formatDate(now, timeZone);
  const nowInTz = getZonedDateParts(now, timeZone);
  const filteredSlots = date === todayInTz
    ? slots.filter((slot) => {
        const [hour, minute] = slot.split(":").map(Number);
        return hour * 60 + minute > nowInTz.hour * 60 + nowInTz.minute;
      })
    : slots;

  return { slots: filteredSlots };
}

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

    const { data: business, error: businessError } = await supabase
      .from("businesses")
      .select("buffer_minutes, business_hours, timezone")
      .eq("id", businessId)
      .single();

    if (businessError || !business) {
      return new Response(JSON.stringify({ error: { code: "business_not_found", message: "Business not found" } }), {
        status: 404,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const endDate = new Date(startDate.getTime() + service.duration_minutes * 60 * 1000);
    const bufferMinutes = business?.buffer_minutes || 15;
    const bufferMs = bufferMinutes * 60 * 1000;
    const timeZone = business.timezone || "America/New_York";
    const localDate = formatDate(startDate, timeZone);
    const dayStartUtc = zonedDateTimeToUtc(localDate, "00:00", timeZone);
    const dayEndUtc = zonedDateTimeToUtc(nextDate(localDate), "00:00", timeZone);

    const checkStart = new Date(startDate.getTime() - bufferMs);
    const checkEnd = new Date(endDate.getTime() + bufferMs);

    const { data: existingAppointments } = await supabase
      .from("appointments")
      .select("id, start_time, end_time")
      .eq("business_id", businessId)
      .in("status", ["pending", "confirmed"])
      .lt("start_time", dayEndUtc.toISOString())
      .gt("end_time", dayStartUtc.toISOString());

    const { slots: bookableSlots, closedMessage } = listBookableSlots({
      date: localDate,
      timeZone,
      businessHours: business.business_hours as Record<string, { open: string; close: string } | null> | null,
      bufferMinutes,
      durationMinutes: service.duration_minutes,
      appointments: (existingAppointments || []).map((appointment) => ({
        start_time: appointment.start_time,
        end_time: appointment.end_time,
      })),
    });

    if (closedMessage) {
      return new Response(JSON.stringify({ error: { code: "business_closed", message: closedMessage } }), {
        status: 409,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const localStart = getZonedDateParts(startDate, timeZone);
    const requestedSlot = `${localStart.hour.toString().padStart(2, "0")}:${localStart.minute.toString().padStart(2, "0")}`;

    if (!bookableSlots.includes(requestedSlot)) {
      return new Response(
        JSON.stringify({ error: { code: "time_conflict", message: "This time slot is no longer available. Please choose another time." } }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const conflicts = (existingAppointments || []).filter((appointment) => {
      const appointmentStart = new Date(appointment.start_time).getTime();
      const appointmentEnd = new Date(appointment.end_time).getTime();
      return appointmentStart < checkEnd.getTime() && appointmentEnd > checkStart.getTime();
    });

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
