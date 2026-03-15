# frozen_string_literal: true

ROUTES = {
  ["GET", "/"] => ["SessionsController", :new],
  ["GET", "/healthz"] => ["HealthController", :index],
  ["GET", "/login"] => ["SessionsController", :new],
  ["POST", "/login"] => ["SessionsController", :create],
  # Keep the dashboard page available to probes that may issue HEAD before GET.
  ["HEAD", "/dashboard"] => ["DashboardController", :show],
  ["GET", "/dashboard"] => ["DashboardController", :show],
  ["POST", "/logout"] => ["SessionsController", :destroy],
}.freeze
