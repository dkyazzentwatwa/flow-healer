-- Allow anonymous/public read of calendly_url from business_settings
CREATE POLICY "Public can read calendly_url"
ON public.business_settings
FOR SELECT
USING (key = 'calendly_url');