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

INSERT INTO public.appointments (business_id, service_id, start_time, end_time, status)
VALUES (
  '22222222-2222-2222-2222-222222222222',
  '33333333-3333-3333-3333-333333333333',
  '2026-03-10T10:00:00Z',
  '2026-03-10T10:30:00Z',
  'confirmed'
);

DO $$
BEGIN
  BEGIN
    INSERT INTO public.appointments (business_id, service_id, start_time, end_time, status)
    VALUES (
      '22222222-2222-2222-2222-222222222222',
      '33333333-3333-3333-3333-333333333333',
      '2026-03-10T10:15:00Z',
      '2026-03-10T10:45:00Z',
      'confirmed'
    );
    RAISE EXCEPTION 'overlapping appointment unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM = 'overlapping appointment unexpectedly succeeded' THEN
        RAISE;
      END IF;
    WHEN OTHERS THEN
      IF position('overlaps with an existing booking' in SQLERRM) = 0 THEN
        RAISE;
      END IF;
  END;
END
$$;
