-- Assert expected subscription ownership behavior.
SELECT
  policyname,
  coalesce(array_to_string(roles, ', '), 'ALL') AS roles,
  cmd,
  qual,
  with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename = 'subscriptions';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'subscriptions'
      AND policyname = 'Owners can insert subscription for own business'
      AND cmd = 'INSERT'
      AND roles IS NOT NULL
      AND roles @> ARRAY['authenticated']::name[]
  ) THEN
    RAISE EXCEPTION 'Missing or misconfigured owner subscription insert policy.';
  END IF;
END;
$$;
