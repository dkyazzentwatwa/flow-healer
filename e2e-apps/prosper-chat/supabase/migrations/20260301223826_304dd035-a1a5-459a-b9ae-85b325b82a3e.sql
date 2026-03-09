
-- Add template_id to bots table to track which industry template was used
ALTER TABLE public.bots ADD COLUMN template_id TEXT;
