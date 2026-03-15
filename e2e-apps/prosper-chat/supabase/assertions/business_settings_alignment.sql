-- Assert business_settings uniqueness and read-policy alignment.
SELECT
  con.conname AS constraint_name,
  rel.relname AS table_name,
  con.contype
FROM pg_constraint AS con
JOIN pg_class AS rel ON rel.oid = con.conrelid
JOIN pg_namespace AS ns ON ns.oid = rel.relnamespace
WHERE ns.nspname = 'public'
  AND rel.relname = 'business_settings';

SELECT
  policyname,
  coalesce(array_to_string(roles, ', '), 'ALL') AS roles,
  cmd,
  qual,
  with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename = 'business_settings';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE table_schema = 'public'
      AND table_name = 'business_settings'
      AND constraint_name = 'business_settings_business_id_key_unique'
      AND constraint_type = 'UNIQUE'
  ) THEN
    RAISE EXCEPTION 'Missing business_settings uniqueness constraint for upsert support.';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.key_column_usage
    WHERE constraint_schema = 'public'
      AND table_name = 'business_settings'
      AND constraint_name = 'business_settings_business_id_key_unique'
      AND column_name IN ('business_id', 'key')
    GROUP BY constraint_name
    HAVING array_agg(column_name ORDER BY ordinal_position)::text[] = ARRAY['business_id', 'key']
  ) THEN
    RAISE EXCEPTION 'business_settings uniqueness constraint is not aligned on (business_id, key).';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'business_settings'
      AND policyname = 'Owners manage settings'
      AND cmd = 'ALL'
      AND roles IS NOT NULL
      AND roles @> ARRAY['authenticated']::name[]
  ) THEN
    RAISE EXCEPTION 'Missing or misconfigured Owners manage settings policy.';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'business_settings'
      AND policyname = 'Public can read calendly_url'
  ) THEN
    RAISE EXCEPTION 'Public calendly_url read policy should remain removed.';
  END IF;
END;
$$;
