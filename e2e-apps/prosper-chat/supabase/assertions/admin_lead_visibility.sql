-- Assert explicit admin visibility remains configured for leads.
SELECT
  policyname,
  coalesce(array_to_string(roles, ', '), 'ALL') AS roles,
  cmd,
  qual,
  with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename = 'leads';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'leads'
      AND policyname = 'Admins can view all leads'
      AND cmd = 'SELECT'
      AND roles IS NOT NULL
      AND roles @> ARRAY['authenticated']::name[]
      AND position('has_role(auth.uid(),' in lower(qual)) > 0
      AND position('admin' in lower(qual)) > 0
  ) THEN
    RAISE EXCEPTION 'Missing or misconfigured explicit admin lead visibility policy.';
  END IF;
END;
$$;
