-- Assert widget bootstrap reads are no longer exposed via public/anon policies.
SELECT
  policyname,
  cmd,
  coalesce(array_to_string(roles, ', '), 'ALL') AS roles,
  qual,
  with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND policyname IN (
    'Public can read business by widget_key',
    'Public can read active services',
    'Public can read active faqs',
    'Public can read active bots',
    'Public can read calendly_url',
    'Anon can create leads',
    'Anon can create appointments',
    'Anon can create conversations',
    'Anon can insert usage records'
  );

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND policyname IN (
        'Public can read business by widget_key',
        'Public can read active services',
        'Public can read active faqs',
        'Public can read active bots',
        'Public can read calendly_url',
        'Anon can create leads',
        'Anon can create appointments',
        'Anon can create conversations',
        'Anon can insert usage records'
      )
  ) THEN
    RAISE EXCEPTION 'Widget bootstrap public/anon policies still present.';
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
    RAISE EXCEPTION 'Expected owner-only bots policy is missing for widget bootstrap.';
  END IF;
END;
$$;
