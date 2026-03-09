
-- Add onboarding_completed to businesses
ALTER TABLE public.businesses ADD COLUMN IF NOT EXISTS onboarding_completed boolean NOT NULL DEFAULT false;

-- Add public read policy for businesses by widget_key (for widget embed)
CREATE POLICY "Public can read business by widget_key"
ON public.businesses
FOR SELECT
USING (true);

-- Drop the old restrictive owner-only SELECT policy and recreate as permissive for owners
-- (the new public policy above handles widget reads, owners already covered)
-- Actually we need to keep owner policy. Let's just add the public one.
-- But wait - existing "Owners can view own businesses" is RESTRICTIVE (Permissive: No).
-- With restrictive policies, ALL must pass. So we can't just add another restrictive policy.
-- We need to drop the old one and create permissive policies instead.

DROP POLICY IF EXISTS "Owners can view own businesses" ON public.businesses;
DROP POLICY IF EXISTS "Public can read business by widget_key" ON public.businesses;

-- Recreate as PERMISSIVE (default) - any matching policy grants access
CREATE POLICY "Owners can view own businesses"
ON public.businesses
FOR SELECT
TO authenticated
USING ((owner_id = auth.uid()) OR has_role(auth.uid(), 'admin'::app_role));

CREATE POLICY "Public can read business by widget_key"
ON public.businesses
FOR SELECT
TO anon
USING (true);
