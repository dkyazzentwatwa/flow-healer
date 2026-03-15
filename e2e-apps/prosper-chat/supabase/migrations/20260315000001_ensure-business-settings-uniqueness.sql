-- Ensure business_settings constraint is properly configured for (business_id, key)
-- This migration is needed because the assertion query has a SQL syntax issue with array casting

DO $$
BEGIN
  -- Drop the existing constraint if the column order is wrong
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'business_settings_business_id_key_unique'
      AND conrelid = 'public.business_settings'::regclass
      AND (SELECT count(*) FROM pg_attribute
           WHERE attrelid = 'public.business_settings'::regclass
           AND attnum = ANY(conkey)
           AND attname IN ('business_id', 'key')) = 2
  ) THEN
    -- Constraint exists and is on the right columns, nothing to do
    NULL;
  ELSE
    -- Need to recreate the constraint
    ALTER TABLE public.business_settings
    DROP CONSTRAINT IF EXISTS business_settings_business_id_key_unique CASCADE;

    ALTER TABLE public.business_settings
    ADD CONSTRAINT business_settings_business_id_key_unique UNIQUE (business_id, key);
  END IF;
END;
$$;
