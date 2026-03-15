-- Fix bot ownership policy to explicitly apply to authenticated users
-- The assertion requires the Owners manage bots policy to have authenticated role

-- Drop the current policy that may have been created for public/all roles
DROP POLICY IF EXISTS "Owners manage bots" ON public.bots;

-- Recreate the policy explicitly for authenticated users
CREATE POLICY "Owners manage bots"
  ON public.bots FOR ALL
  TO authenticated
  USING (owns_business(business_id))
  WITH CHECK (owns_business(business_id));
