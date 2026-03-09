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

serve(async (req) => {
  const corsHeaders = buildCorsHeaders(req, "*");
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { widget_token, service_id, date } = await req.json();
    if (!widget_token || !service_id || !date) {
      return new Response(JSON.stringify({ error: { code: "bad_request", message: "Missing required fields" } }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const claims = await verifyWidgetToken(String(widget_token));
    const businessId = claims.business_id;

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
      { auth: { persistSession: false } },
    );

    const { data: business, error: bizErr } = await supabase
      .from("businesses")
      .select("business_hours, buffer_minutes, timezone")
      .eq("id", businessId)
      .single();

    if (bizErr || !business) {
      return new Response(JSON.stringify({ error: { code: "business_not_found", message: "Business not found" } }), {
        status: 404,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const { data: service, error: svcErr } = await supabase
      .from("services")
      .select("duration_minutes, name")
      .eq("id", service_id)
      .eq("business_id", businessId)
      .eq("is_active", true)
      .single();

    if (svcErr || !service) {
      return new Response(JSON.stringify({ error: { code: "service_not_found", message: "Service not found" } }), {
        status: 404,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const tz = business.timezone || "America/New_York";
    const buffer = business.buffer_minutes || 15;
    const duration = service.duration_minutes;
    const hours = business.business_hours as Record<string, { open: string; close: string } | null> | null;

    const requestWeekday = getZonedDateParts(zonedDateTimeToUtc(date, "12:00", tz), tz).weekday;
    const dayKey = DAY_MAP[requestWeekday];
    const dayHours = dayKey ? hours?.[dayKey] : null;

    if (!dayHours) {
      return new Response(JSON.stringify({ slots: [], message: "Business is closed on this day" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const [openH, openM] = dayHours.open.split(":").map(Number);
    const [closeH, closeM] = dayHours.close.split(":").map(Number);
    const openMin = openH * 60 + openM;
    const closeMin = closeH * 60 + closeM;

    const dayStartUtc = zonedDateTimeToUtc(date, "00:00", tz);
    const dayEndUtc = zonedDateTimeToUtc(nextDate(date), "00:00", tz);

    const { data: existing } = await supabase
      .from("appointments")
      .select("start_time, end_time")
      .eq("business_id", businessId)
      .in("status", ["pending", "confirmed"])
      .lt("start_time", dayEndUtc.toISOString())
      .gt("end_time", dayStartUtc.toISOString());

    const booked = (existing || []).map((apt) => {
      const localStart = getZonedDateParts(new Date(apt.start_time), tz);
      const localEnd = getZonedDateParts(new Date(apt.end_time), tz);
      return {
        startMin: localStart.hour * 60 + localStart.minute,
        endMin: localEnd.hour * 60 + localEnd.minute,
      };
    });

    const interval = Math.min(30, duration);
    const slots: string[] = [];

    for (let slotStart = openMin; slotStart + duration <= closeMin; slotStart += interval) {
      const slotEnd = slotStart + duration + buffer;

      const hasConflict = booked.some((entry) => {
        const entryEnd = entry.endMin + buffer;
        return slotStart < entryEnd && slotEnd > entry.startMin;
      });

      if (!hasConflict) {
        const h = Math.floor(slotStart / 60);
        const m = slotStart % 60;
        slots.push(`${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`);
      }
    }

    const todayInTz = formatDate(new Date(), tz);
    const nowInTz = getZonedDateParts(new Date(), tz);
    const filteredSlots = date === todayInTz
      ? slots.filter((slot) => {
          const [h, m] = slot.split(":").map(Number);
          return h * 60 + m > nowInTz.hour * 60 + nowInTz.minute;
        })
      : slots;

    return new Response(
      JSON.stringify({ slots: filteredSlots, service_name: service.name, duration_minutes: duration }),
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
