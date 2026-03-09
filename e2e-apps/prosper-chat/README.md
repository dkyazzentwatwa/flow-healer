# Prosper Chat

AI receptionist web app (Vite + React + Supabase) with dashboard management, embedded widget chat, booking, and Stripe billing.

## Tech Stack
- Frontend: Vite, React, TypeScript, Tailwind, React Query
- Backend: Supabase Postgres + Edge Functions
- Billing: Stripe subscriptions

## Local Development
1. Copy `.env.example` to `.env` and set `VITE_SUPABASE_*` values.
2. Install and run:

```sh
npm ci
npm run dev
```

## Quality Checks
```sh
npm run lint
npm run test
npm run build
```

## Supabase Edge Function Secrets
Set these in your Supabase project for production:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `STRIPE_SECRET_KEY`
- `LOVABLE_API_KEY`
- `WIDGET_TOKEN_SECRET` (long random string; used to sign widget tokens)
- `APP_BASE_URL` (for Stripe success/cancel/portal return URLs)
- `CORS_ALLOWED_ORIGINS` (comma-separated allowlist, e.g. `https://app.example.com,https://staging.example.com`)

## Deployment Notes
- `BrowserRouter` requires SPA rewrites. Use `netlify.toml` or `vercel.json` in this repo.
- Deploy frontend and edge-function changes together.
- Apply migrations before serving traffic:

```sh
supabase db push
supabase functions deploy
```

- Runtime smoke endpoint: `GET /healthz`

## Security Posture
- Widget data now comes from `widget-bootstrap` with signed `widget_token`.
- Booking and availability functions validate `widget_token` server-side.
- Billing functions enforce origin allowlist and require verified JWT.
- Public table-read policies for widget data are removed in latest migration.

## CI
GitHub Actions workflow `.github/workflows/ci.yml` runs install, lint, test, and build on push/PR.
