-- Keep admin lead visibility explicitly modeled as a dedicated policy.
DO $$
BEGIN
  IF to_regclass('public.leads') IS NULL THEN
    RAISE NOTICE 'Skipping admin lead visibility migration: public.leads does not exist yet.';
    RETURN;
  END IF;

  DROP POLICY IF EXISTS "Admins can view all leads" ON public.leads;

  CREATE POLICY "Admins can view all leads"
  ON public.leads
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin'));
END;
$$;
