
-- Enum for user roles
CREATE TYPE public.app_role AS ENUM ('admin', 'owner');

-- Enum for lead status
CREATE TYPE public.lead_status AS ENUM ('new', 'contacted', 'qualified', 'converted', 'lost');

-- Enum for appointment status
CREATE TYPE public.appointment_status AS ENUM ('pending', 'confirmed', 'cancelled', 'completed', 'no_show');

-- ============================================================
-- TABLES
-- ============================================================

-- Businesses
CREATE TABLE public.businesses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  widget_key TEXT NOT NULL UNIQUE DEFAULT 'biz_' || substr(md5(random()::text || clock_timestamp()::text), 1, 12),
  phone TEXT,
  email TEXT,
  address TEXT,
  timezone TEXT DEFAULT 'America/New_York',
  business_hours JSONB DEFAULT '{"mon":{"open":"09:00","close":"17:00"},"tue":{"open":"09:00","close":"17:00"},"wed":{"open":"09:00","close":"17:00"},"thu":{"open":"09:00","close":"17:00"},"fri":{"open":"09:00","close":"17:00"},"sat":null,"sun":null}'::jsonb,
  buffer_minutes INTEGER DEFAULT 15,
  welcome_message TEXT DEFAULT 'Hi! How can I help you today?',
  escalation_phone TEXT,
  escalation_email TEXT,
  privacy_store_transcripts BOOLEAN DEFAULT false,
  privacy_retention_days INTEGER DEFAULT 30,
  disclaimer_text TEXT DEFAULT 'Please don''t share sensitive personal, medical, or payment information here.',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- User roles (separate table per security requirements)
CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role app_role NOT NULL,
  UNIQUE(user_id, role)
);

-- Services
CREATE TABLE public.services (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  duration_minutes INTEGER NOT NULL DEFAULT 30,
  price_text TEXT,
  is_active BOOLEAN DEFAULT true,
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FAQs
CREATE TABLE public.faqs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  sort_order INTEGER DEFAULT 0,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Leads
CREATE TABLE public.leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  first_name TEXT,
  email TEXT,
  phone TEXT,
  source TEXT DEFAULT 'widget',
  status lead_status NOT NULL DEFAULT 'new',
  is_returning BOOLEAN DEFAULT false,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Appointments
CREATE TABLE public.appointments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
  service_id UUID REFERENCES public.services(id) ON DELETE SET NULL,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NOT NULL,
  status appointment_status NOT NULL DEFAULT 'pending',
  google_event_id TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Conversations (chat transcripts)
CREATE TABLE public.conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
  messages JSONB DEFAULT '[]'::jsonb,
  intent TEXT,
  escalated BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Business settings (key-value pairs for extensible config)
CREATE TABLE public.business_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value JSONB,
  UNIQUE(business_id, key)
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_businesses_owner ON public.businesses(owner_id);
CREATE INDEX idx_businesses_widget_key ON public.businesses(widget_key);
CREATE INDEX idx_services_business ON public.services(business_id);
CREATE INDEX idx_faqs_business ON public.faqs(business_id);
CREATE INDEX idx_leads_business ON public.leads(business_id);
CREATE INDEX idx_appointments_business ON public.appointments(business_id);
CREATE INDEX idx_appointments_start ON public.appointments(start_time);
CREATE INDEX idx_conversations_business ON public.conversations(business_id);

-- ============================================================
-- ENABLE RLS
-- ============================================================
ALTER TABLE public.businesses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.services ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.faqs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_settings ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- HELPER FUNCTIONS (security definer to avoid RLS recursion)
-- ============================================================

CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role app_role)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles
    WHERE user_id = _user_id AND role = _role
  )
$$;

CREATE OR REPLACE FUNCTION public.owns_business(_business_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.businesses
    WHERE id = _business_id AND owner_id = auth.uid()
  )
$$;

-- ============================================================
-- RLS POLICIES
-- ============================================================

-- user_roles
CREATE POLICY "Users can view own roles" ON public.user_roles
  FOR SELECT USING (user_id = auth.uid());

-- businesses
CREATE POLICY "Owners can view own businesses" ON public.businesses
  FOR SELECT TO authenticated USING (owner_id = auth.uid() OR public.has_role(auth.uid(), 'admin'));

CREATE POLICY "Owners can insert businesses" ON public.businesses
  FOR INSERT TO authenticated WITH CHECK (owner_id = auth.uid());

CREATE POLICY "Owners can update own businesses" ON public.businesses
  FOR UPDATE TO authenticated USING (owner_id = auth.uid());

CREATE POLICY "Owners can delete own businesses" ON public.businesses
  FOR DELETE TO authenticated USING (owner_id = auth.uid());

-- services: owners CRUD, public read by widget_key via edge function
CREATE POLICY "Owners manage services" ON public.services
  FOR ALL TO authenticated USING (public.owns_business(business_id)) WITH CHECK (public.owns_business(business_id));

CREATE POLICY "Public can read active services" ON public.services
  FOR SELECT TO anon USING (is_active = true);

-- faqs: owners CRUD, public read
CREATE POLICY "Owners manage faqs" ON public.faqs
  FOR ALL TO authenticated USING (public.owns_business(business_id)) WITH CHECK (public.owns_business(business_id));

CREATE POLICY "Public can read active faqs" ON public.faqs
  FOR SELECT TO anon USING (is_active = true);

-- leads: owners read/update, anon insert via edge function
CREATE POLICY "Owners manage leads" ON public.leads
  FOR ALL TO authenticated USING (public.owns_business(business_id)) WITH CHECK (public.owns_business(business_id));

CREATE POLICY "Anon can create leads" ON public.leads
  FOR INSERT TO anon WITH CHECK (true);

-- appointments: owners read/update, anon insert via edge function
CREATE POLICY "Owners manage appointments" ON public.appointments
  FOR ALL TO authenticated USING (public.owns_business(business_id)) WITH CHECK (public.owns_business(business_id));

CREATE POLICY "Anon can create appointments" ON public.appointments
  FOR INSERT TO anon WITH CHECK (true);

-- conversations: owners read, anon insert
CREATE POLICY "Owners manage conversations" ON public.conversations
  FOR ALL TO authenticated USING (public.owns_business(business_id)) WITH CHECK (public.owns_business(business_id));

CREATE POLICY "Anon can create conversations" ON public.conversations
  FOR INSERT TO anon WITH CHECK (true);

-- business_settings: owners only
CREATE POLICY "Owners manage settings" ON public.business_settings
  FOR ALL TO authenticated USING (public.owns_business(business_id)) WITH CHECK (public.owns_business(business_id));

-- ============================================================
-- TRIGGERS for updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public;

CREATE TRIGGER trg_businesses_updated BEFORE UPDATE ON public.businesses FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER trg_services_updated BEFORE UPDATE ON public.services FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER trg_faqs_updated BEFORE UPDATE ON public.faqs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER trg_leads_updated BEFORE UPDATE ON public.leads FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER trg_appointments_updated BEFORE UPDATE ON public.appointments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER trg_conversations_updated BEFORE UPDATE ON public.conversations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- ============================================================
-- Auto-create business on signup (trigger)
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.businesses (owner_id, name)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'business_name', 'My Business'));
  
  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'owner');
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
