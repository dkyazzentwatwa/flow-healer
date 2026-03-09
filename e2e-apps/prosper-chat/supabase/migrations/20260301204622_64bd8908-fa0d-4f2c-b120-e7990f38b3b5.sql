
-- Create plan enum
CREATE TYPE public.subscription_plan AS ENUM ('free', 'pro', 'agency');

-- Create subscription status enum
CREATE TYPE public.subscription_status AS ENUM ('active', 'cancelled', 'past_due');

-- Create usage record type enum
CREATE TYPE public.usage_type AS ENUM ('chat', 'appointment_booked', 'lead_captured');

-- Create subscriptions table
CREATE TABLE public.subscriptions (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  plan public.subscription_plan NOT NULL DEFAULT 'free',
  status public.subscription_status NOT NULL DEFAULT 'active',
  current_period_start TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  current_period_end TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (now() + interval '30 days'),
  stripe_subscription_id TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  UNIQUE(business_id)
);

-- Create usage_records table
CREATE TABLE public.usage_records (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  type public.usage_type NOT NULL,
  recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Create index for fast usage queries
CREATE INDEX idx_usage_records_business_period ON public.usage_records (business_id, recorded_at);
CREATE INDEX idx_usage_records_type ON public.usage_records (business_id, type, recorded_at);

-- Enable RLS
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_records ENABLE ROW LEVEL SECURITY;

-- Subscriptions RLS: owners can view their own
CREATE POLICY "Owners can view own subscription"
  ON public.subscriptions FOR SELECT
  USING (owns_business(business_id));

-- Admins can view all subscriptions
CREATE POLICY "Admins can view all subscriptions"
  ON public.subscriptions FOR SELECT
  USING (has_role(auth.uid(), 'admin'::app_role));

-- Only system (service role) can insert/update subscriptions
-- No insert/update policies for regular users

-- Usage records RLS: owners can view their own
CREATE POLICY "Owners can view own usage"
  ON public.usage_records FOR SELECT
  USING (owns_business(business_id));

-- Admins can view all usage
CREATE POLICY "Admins can view all usage"
  ON public.usage_records FOR SELECT
  USING (has_role(auth.uid(), 'admin'::app_role));

-- Anon can insert usage records (from chat widget edge function via service role, but also allow insert for valid businesses)
CREATE POLICY "Anon can insert usage records"
  ON public.usage_records FOR INSERT
  WITH CHECK (EXISTS (SELECT 1 FROM businesses WHERE businesses.id = usage_records.business_id));

-- Updated at trigger for subscriptions
CREATE TRIGGER update_subscriptions_updated_at
  BEFORE UPDATE ON public.subscriptions
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at();

-- Update handle_new_user to also create a free subscription
CREATE OR REPLACE FUNCTION public.handle_new_user()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $function$
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
  
  RETURN NEW;
END;
$function$;

-- Backfill: create free subscriptions for existing businesses that don't have one
INSERT INTO public.subscriptions (business_id, plan, status)
SELECT b.id, 'free', 'active'
FROM public.businesses b
WHERE NOT EXISTS (SELECT 1 FROM public.subscriptions s WHERE s.business_id = b.id);
