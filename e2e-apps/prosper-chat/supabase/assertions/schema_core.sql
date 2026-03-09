DO $$
DECLARE
  required_tables text[] := ARRAY[
    'businesses',
    'user_roles',
    'services',
    'faqs',
    'leads',
    'appointments',
    'conversations',
    'business_settings',
    'subscriptions',
    'usage_records',
    'bots'
  ];
  required_functions text[] := ARRAY[
    'has_role',
    'owns_business',
    'update_updated_at',
    'handle_new_user',
    'prevent_appointment_overlap'
  ];
  item text;
BEGIN
  FOREACH item IN ARRAY required_tables LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = item
    ) THEN
      RAISE EXCEPTION 'missing required table: %', item;
    END IF;
  END LOOP;

  FOREACH item IN ARRAY required_functions LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_proc proc
      JOIN pg_namespace ns ON ns.oid = proc.pronamespace
      WHERE ns.nspname = 'public' AND proc.proname = item
    ) THEN
      RAISE EXCEPTION 'missing required function: %', item;
    END IF;
  END LOOP;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'trg_prevent_appointment_overlap'
  ) THEN
    RAISE EXCEPTION 'missing required trigger: trg_prevent_appointment_overlap';
  END IF;
END
$$;
