DO $$
DECLARE
  required_policies text[] := ARRAY[
    'Owners can view own businesses',
    'Owners manage services',
    'Owners manage faqs',
    'Owners manage leads',
    'Owners manage appointments',
    'Owners manage conversations',
    'Owners manage settings',
    'Owners can view own subscription',
    'Owners can view own usage',
    'Admins can view all subscriptions',
    'Admins can view all usage',
    'Owners manage bots'
  ];
  removed_public_policies text[] := ARRAY[
    'Public can read business by widget_key',
    'Public can read active services',
    'Public can read active faqs',
    'Public can read active bots',
    'Public can read calendly_url',
    'Anon can create leads',
    'Anon can create appointments',
    'Anon can create conversations',
    'Anon can insert usage records'
  ];
  item text;
BEGIN
  FOREACH item IN ARRAY required_policies LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_policies
      WHERE schemaname = 'public' AND policyname = item
    ) THEN
      RAISE EXCEPTION 'missing required policy: %', item;
    END IF;
  END LOOP;

  FOREACH item IN ARRAY removed_public_policies LOOP
    IF EXISTS (
      SELECT 1
      FROM pg_policies
      WHERE schemaname = 'public' AND policyname = item
    ) THEN
      RAISE EXCEPTION 'policy should have been removed: %', item;
    END IF;
  END LOOP;
END
$$;
