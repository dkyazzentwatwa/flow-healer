-- Tighten public data exposure now that widget-bootstrap edge function serves scoped data
DROP POLICY IF EXISTS "Public can read business by widget_key" ON public.businesses;
DROP POLICY IF EXISTS "Public can read active services" ON public.services;
DROP POLICY IF EXISTS "Public can read active faqs" ON public.faqs;
DROP POLICY IF EXISTS "Public can read active bots" ON public.bots;
DROP POLICY IF EXISTS "Public can read calendly_url" ON public.business_settings;
DROP POLICY IF EXISTS "Anon can create leads" ON public.leads;
DROP POLICY IF EXISTS "Anon can create appointments" ON public.appointments;
DROP POLICY IF EXISTS "Anon can create conversations" ON public.conversations;
DROP POLICY IF EXISTS "Anon can insert usage records" ON public.usage_records;

-- Prevent overlapping appointments per business for active booking statuses
CREATE OR REPLACE FUNCTION public.prevent_appointment_overlap()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.status NOT IN ('pending', 'confirmed') THEN
    RETURN NEW;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.appointments a
    WHERE a.business_id = NEW.business_id
      AND a.id <> COALESCE(NEW.id, '00000000-0000-0000-0000-000000000000'::uuid)
      AND a.status IN ('pending', 'confirmed')
      AND a.start_time < NEW.end_time
      AND a.end_time > NEW.start_time
  ) THEN
    RAISE EXCEPTION 'Appointment overlaps with an existing booking';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_prevent_appointment_overlap ON public.appointments;
CREATE TRIGGER trg_prevent_appointment_overlap
BEFORE INSERT OR UPDATE ON public.appointments
FOR EACH ROW
EXECUTE FUNCTION public.prevent_appointment_overlap();
