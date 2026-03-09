-- Allow business owners to insert subscriptions for their own businesses
CREATE POLICY "Owners can insert subscription for own business"
ON public.subscriptions
FOR INSERT
WITH CHECK (owns_business(business_id));
