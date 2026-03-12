# frozen_string_literal: true

ROUTES = {
  ["GET", "/"] => ["SessionsController", :new],
  ["GET", "/healthz"] => ["HealthController", :index],
  ["GET", "/login"] => ["SessionsController", :new],
  ["POST", "/login"] => ["SessionsController", :create],
  ["GET", "/dashboard"] => ["DashboardController", :show],
  ["POST", "/logout"] => ["SessionsController", :destroy],
}.freeze
