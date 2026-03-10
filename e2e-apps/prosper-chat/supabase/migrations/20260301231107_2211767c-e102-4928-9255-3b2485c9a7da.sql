-- Add unique constraint on business_settings for upsert support
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'business_settings_business_id_key_unique'
      AND conrelid = 'public.business_settings'::regclass
  ) THEN
    ALTER TABLE public.business_settings
    ADD CONSTRAINT business_settings_business_id_key_unique UNIQUE (business_id, key);
  END IF;
END;
$$;

-- Allow anon to read business_settings for Google Calendar check (non-sensitive keys only via RLS)
-- The existing "Owners manage settings" policy covers owner access
-- We need service role access for edge functions which already bypasses RLS
