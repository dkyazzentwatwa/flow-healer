
-- Tighten anon INSERT policies to require a valid business_id
DROP POLICY "Anon can create leads" ON public.leads;
DROP POLICY "Anon can create appointments" ON public.appointments;
DROP POLICY "Anon can create conversations" ON public.conversations;

CREATE POLICY "Anon can create leads" ON public.leads
  FOR INSERT TO anon WITH CHECK (
    EXISTS (SELECT 1 FROM public.businesses WHERE id = business_id)
  );

CREATE POLICY "Anon can create appointments" ON public.appointments
  FOR INSERT TO anon WITH CHECK (
    EXISTS (SELECT 1 FROM public.businesses WHERE id = business_id)
  );

CREATE POLICY "Anon can create conversations" ON public.conversations
  FOR INSERT TO anon WITH CHECK (
    EXISTS (SELECT 1 FROM public.businesses WHERE id = business_id)
  );
