-- Keep business_settings uniqueness and read policy aligned for owner-only settings access.
-- Ensure upserts use a stable unique constraint identifier on (business_id, key).
DO $$
DECLARE
  existing_constraint_name text;
BEGIN
  SELECT constraint_name
  INTO existing_constraint_name
  FROM (
    SELECT
      tc.constraint_name,
      array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_schema = kcu.constraint_schema
      AND tc.constraint_name = kcu.constraint_name
      AND tc.table_name = kcu.table_name
    WHERE tc.table_schema = 'public'
      AND tc.table_name = 'business_settings'
      AND tc.constraint_type = 'UNIQUE'
    GROUP BY tc.constraint_name
  ) AS unique_constraints
  WHERE columns = ARRAY['business_id', 'key']
  LIMIT 1;

  IF existing_constraint_name IS NULL THEN
    ALTER TABLE public.business_settings
    ADD CONSTRAINT business_settings_business_id_key_unique UNIQUE (business_id, key);
  ELSIF existing_constraint_name <> 'business_settings_business_id_key_unique' THEN
    EXECUTE format(
      'ALTER TABLE public.business_settings RENAME CONSTRAINT %I TO business_settings_business_id_key_unique',
      existing_constraint_name
    );
  END IF;

  DROP POLICY IF EXISTS "Owners manage settings" ON public.business_settings;
  CREATE POLICY "Owners manage settings"
  ON public.business_settings
  FOR ALL
  TO authenticated
  USING (public.owns_business(business_id))
  WITH CHECK (public.owns_business(business_id));

  DROP POLICY IF EXISTS "Public can read calendly_url" ON public.business_settings;
END;
$$;
