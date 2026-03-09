
-- Create bots table
CREATE TABLE public.bots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT 'Main Bot',
  widget_key TEXT NOT NULL DEFAULT ('bot_' || substr(md5(random()::text || clock_timestamp()::text), 1, 12)),
  welcome_message TEXT DEFAULT 'Hi! How can I help you today?',
  disclaimer_text TEXT DEFAULT 'Please don''t share sensitive personal, medical, or payment information here.',
  system_prompt TEXT,
  faq_ids UUID[],
  service_ids UUID[],
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Unique constraint on widget_key
CREATE UNIQUE INDEX bots_widget_key_idx ON public.bots (widget_key);

-- Index for business lookup
CREATE INDEX bots_business_id_idx ON public.bots (business_id);

-- Updated_at trigger
CREATE TRIGGER update_bots_updated_at
  BEFORE UPDATE ON public.bots
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at();

-- Enable RLS
ALTER TABLE public.bots ENABLE ROW LEVEL SECURITY;

-- Owners can manage their bots
CREATE POLICY "Owners manage bots"
  ON public.bots FOR ALL
  USING (owns_business(business_id))
  WITH CHECK (owns_business(business_id));

-- Public can read active bots by widget_key (for embed)
CREATE POLICY "Public can read active bots"
  ON public.bots FOR SELECT
  USING (is_active = true);

-- Seed a default bot for every existing business
INSERT INTO public.bots (business_id, name, welcome_message, disclaimer_text)
SELECT id, 'Main Bot',
  COALESCE(welcome_message, 'Hi! How can I help you today?'),
  COALESCE(disclaimer_text, 'Please don''t share sensitive personal, medical, or payment information here.')
FROM public.businesses;

-- Update handle_new_user to also create a default bot
CREATE OR REPLACE FUNCTION public.handle_new_user()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
DECLARE
  new_business_id UUID;
BEGIN
  INSERT INTO public.businesses (owner_id, name)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'business_name', 'My Business'))
  RETURNING id INTO new_business_id;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'owner');

  INSERT INTO public.subscriptions (business_id, plan, status)
  VALUES (new_business_id, 'free', 'active');

  INSERT INTO public.bots (business_id, name)
  VALUES (new_business_id, 'Main Bot');

  RETURN NEW;
END;
$$;
