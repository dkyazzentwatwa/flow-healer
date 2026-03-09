-- Add unique constraint on business_settings for upsert support
ALTER TABLE public.business_settings
ADD CONSTRAINT business_settings_business_id_key_unique UNIQUE (business_id, key);

-- Allow anon to read business_settings for Google Calendar check (non-sensitive keys only via RLS)
-- The existing "Owners manage settings" policy covers owner access
-- We need service role access for edge functions which already bypasses RLS