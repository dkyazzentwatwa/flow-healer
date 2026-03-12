# frozen_string_literal: true

require "json"

class HealthController
  def index(request:, session_user:)
    {
      status: 200,
      content_type: "application/json",
      body: JSON.generate(status: "ok", fixture_profile: session_user)
    }
  end
end
