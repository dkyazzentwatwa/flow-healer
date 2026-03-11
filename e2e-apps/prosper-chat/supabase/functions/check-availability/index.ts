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

    const dayStartUtc = zonedDateTimeToUtc(date, "00:00", tz);
    const dayEndUtc = zonedDateTimeToUtc(nextDate(date), "00:00", tz);

    const { data: existing } = await supabase
      .from("appointments")
      .select("start_time, end_time")
      .eq("business_id", businessId)
      .in("status", ["pending", "confirmed"])
      .lt("start_time", dayEndUtc.toISOString())
      .gt("end_time", dayStartUtc.toISOString());

    const { slots: filteredSlots, closedMessage } = listBookableSlots({
      date,
      timeZone: tz,
      businessHours: hours,
      bufferMinutes: buffer,
      durationMinutes: duration,
      appointments: existing || [],
    });

    if (closedMessage) {
      return new Response(JSON.stringify({ slots: [], message: closedMessage }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

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
