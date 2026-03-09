INSERT INTO auth.users (
  instance_id,
  id,
  aud,
  role,
  email,
  encrypted_password,
  email_confirmed_at,
  raw_app_meta_data,
  raw_user_meta_data,
  created_at,
  updated_at
)
VALUES (
  '00000000-0000-0000-0000-000000000000',
  '11111111-1111-1111-1111-111111111111',
  'authenticated',
  'authenticated',
  'owner@example.com',
  'x',
  now(),
  '{}'::jsonb,
  '{}'::jsonb,
  now(),
  now()
);

INSERT INTO public.businesses (id, owner_id, name, widget_key)
VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'Demo Biz', 'biz_demo_seed');

INSERT INTO public.services (id, business_id, name, duration_minutes, is_active)
VALUES ('33333333-3333-3333-3333-333333333333', '22222222-2222-2222-2222-222222222222', 'Consult', 30, true);

SET LOCAL ROLE "anon";
SELECT set_config('request.jwt.claim.role', 'anon', true);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.businesses
    WHERE id = '22222222-2222-2222-2222-222222222222'
  ) THEN
    RAISE EXCEPTION 'anon unexpectedly read businesses rows';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.services
    WHERE business_id = '22222222-2222-2222-2222-222222222222'
  ) THEN
    RAISE EXCEPTION 'anon unexpectedly read services rows';
  END IF;
END
$$;

DO $$
BEGIN
  BEGIN
    INSERT INTO public.leads (business_id, first_name)
    VALUES ('22222222-2222-2222-2222-222222222222', 'Anon Lead');
    RAISE EXCEPTION 'anon lead insert unexpectedly succeeded';
  EXCEPTION
    WHEN insufficient_privilege OR raise_exception THEN
      IF SQLERRM = 'anon lead insert unexpectedly succeeded' THEN
        RAISE;
      END IF;
    WHEN OTHERS THEN
      IF position('row-level security' in SQLERRM) = 0 THEN
        RAISE;
      END IF;
  END;
END
$$;
