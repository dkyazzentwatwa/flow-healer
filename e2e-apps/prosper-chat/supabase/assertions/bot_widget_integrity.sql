-- Assert expected bot/widget policy and schema coupling.
SELECT
  c.conname AS constraint_name,
  c.contype,
  rel.relname AS table_name
FROM pg_constraint AS c
JOIN pg_class AS rel ON rel.oid = c.conrelid
JOIN pg_namespace AS ns ON ns.oid = rel.relnamespace
WHERE ns.nspname = 'public'
  AND rel.relname = 'bots'
  AND c.conname = 'bots_business_id_fkey';

SELECT
  policyname,
  coalesce(array_to_string(roles, ', '), 'ALL') AS roles,
  cmd,
  qual,
  with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename = 'bots';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE table_schema = 'public'
      AND table_name = 'bots'
      AND constraint_name = 'bots_business_id_fkey'
      AND constraint_type = 'FOREIGN KEY'
  ) THEN
    RAISE EXCEPTION 'Missing bots -> businesses foreign key.';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'bots'
      AND indexname = 'bots_widget_key_idx'
  ) THEN
    RAISE EXCEPTION 'Missing public.bots unique widget key index.';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'bots'
      AND policyname = 'Owners manage bots'
      AND cmd = 'ALL'
      AND roles IS NOT NULL
      AND roles @> ARRAY['authenticated']::name[]
  ) THEN
    RAISE EXCEPTION 'Missing or misconfigured bot owner policy.';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'bots'
      AND policyname = 'Public can read active bots'
  ) THEN
    RAISE EXCEPTION 'Public bot policy is no longer expected for widget bootstrap.';
  END IF;
END;
$$;
