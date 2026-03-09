-- Remove widget-bootstrap public surface area and keep data scoped to edge-function service-role paths.
DO $$
BEGIN
  IF to_regclass('public.businesses') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Public can read business by widget_key" ON public.businesses;
  END IF;

  IF to_regclass('public.services') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Public can read active services" ON public.services;
  END IF;

  IF to_regclass('public.faqs') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Public can read active faqs" ON public.faqs;
  END IF;

  IF to_regclass('public.leads') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Anon can create leads" ON public.leads;
  END IF;

  IF to_regclass('public.appointments') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Anon can create appointments" ON public.appointments;
  END IF;

  IF to_regclass('public.conversations') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Anon can create conversations" ON public.conversations;
  END IF;

  IF to_regclass('public.usage_records') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Anon can insert usage records" ON public.usage_records;
  END IF;

  IF to_regclass('public.business_settings') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Public can read calendly_url" ON public.business_settings;
  END IF;

  IF to_regclass('public.bots') IS NOT NULL THEN
    DROP POLICY IF EXISTS "Public can read active bots" ON public.bots;
  END IF;
END;
$$;
