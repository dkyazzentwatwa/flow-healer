-- Keep bot/widget data path connected to owner-based policies while avoiding
-- broad public exposure.
DO $$
BEGIN
  IF to_regclass('public.bots') IS NULL THEN
    RAISE NOTICE 'Skipping bot widget policy bootstrap: public.bots does not exist yet.';
    RETURN;
  END IF;

  -- Do not expose bot records directly to anon/public contexts; owner policies
  -- drive dashboard CRUD and service-role calls drive widget bootstrap.
  DROP POLICY IF EXISTS "Public can read active bots" ON public.bots;
  DROP POLICY IF EXISTS "Owners manage bots" ON public.bots;

  CREATE POLICY "Owners manage bots"
    ON public.bots
    FOR ALL TO authenticated
    USING (public.owns_business(business_id))
    WITH CHECK (public.owns_business(business_id));

  CREATE INDEX IF NOT EXISTS bots_widget_key_idx ON public.bots (widget_key);
  CREATE INDEX IF NOT EXISTS bots_business_id_idx ON public.bots (business_id);
END;
$$;
